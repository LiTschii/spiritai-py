# Renamed the file for clarity
import flask
from flask import Flask, request, jsonify
import weaviate
import weaviate.classes as wvc
import weaviate.classes.query as wq # Import for filters and metadata
# Fix import error - CollectionNotFoundError doesn't exist in weaviate.exceptions
# Use custom exception handling instead
import os
from dotenv import load_dotenv
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import uuid # Import uuid for potential fallback titles

# Set up logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load environment variables (if needed for Weaviate connection)
load_dotenv("/home/admin/apps/marimo/notebooks/.env") # Adjust path if necessary

# --- Weaviate Connection ---
try:
    WEAVIATE_PASSWORD = os.getenv("PASSWORD") # Or your specific Weaviate API key env var
    if not WEAVIATE_PASSWORD:
        raise ValueError("Weaviate password/API key not found in environment variables.")

    client = weaviate.connect_to_local(
        port=8080,
        grpc_port=50051,
        # Use the loaded password/key for authentication
        auth_credentials=wvc.init.Auth.api_key(WEAVIATE_PASSWORD)
    )
    client.connect() # Explicitly connect and check
    logger.info(f"Successfully connected to Weaviate at {client.get_meta()['hostname']}")
except Exception as e:
    logger.error(f"Failed to connect to Weaviate: {str(e)}", exc_info=True)
    # Depending on the setup, you might want the app to exit if Weaviate isn't available
    raise ConnectionError(f"Could not connect to Weaviate: {e}") from e

# --- Helper Function for Serialization ---
def process_properties(properties: Dict[str, Any]) -> Dict[str, Any]:
    """Converts Weaviate property values to JSON-serializable formats."""
    processed = {}
    if not properties:
        return processed
    for key, value in properties.items():
        if isinstance(value, (datetime)):
            processed[key] = value.isoformat()
        elif isinstance(value, (uuid.UUID)):
             processed[key] = str(value)
        # Handle GeoCoordinate objects
        elif hasattr(value, 'latitude') and hasattr(value, 'longitude'):
            processed[key] = {"latitude": value.latitude, "longitude": value.longitude}
        elif isinstance(value, (list, dict)):
             # Recursively process nested structures
             if isinstance(value, list):
                 processed[key] = [process_single_value(item) for item in value]
             else:  # dict
                 processed[key] = {k: process_single_value(v) for k, v in value.items()}
        else:
            # Assume other types are directly serializable (int, float, str, bool)
            processed[key] = value
    return processed

def process_single_value(value):
    """Process a single value to make it JSON serializable."""
    if isinstance(value, (datetime)):
        return value.isoformat()
    elif isinstance(value, (uuid.UUID)):
        return str(value)
    elif hasattr(value, 'latitude') and hasattr(value, 'longitude'):
        return {"latitude": value.latitude, "longitude": value.longitude}
    elif isinstance(value, (list)):
        return [process_single_value(item) for item in value]
    elif isinstance(value, (dict)):
        return {k: process_single_value(v) for k, v in value.items()}
    return value

# --- API Endpoints ---

@app.route('/collections', methods=['GET'])
def list_collections():
    """Lists the names of all collections in Weaviate."""
    try:
        collections_dict = client.collections.list_all()
        # Extract just the names (keys of the dictionary)
        collection_names = list(collections_dict.keys())
        logger.info(f"Returning collection list: {collection_names}")
        return jsonify({"collections": collection_names})
    except Exception as e:
        logger.error(f"Error listing collections: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to retrieve collections", "details": str(e)}), 500

@app.route('/query', methods=['POST'])
def query_collection():
    """
    Performs a vector search (nearText) on a specified collection with optional
    filtering and field exclusion.

    JSON Request Body:
    {
        "collection_name": "your_collection",  // Required
        "query": "your search query text",    // Required
        "top_k": 10,                          // Optional (default: 5)
        "exclude_fields": ["field1", "field2"],// Optional (default: [])
        "filters": {                          // Optional (default: no filters)
            "operator": "And",                // "And" or "Or" (default: "And")
            "conditions": [
                {"field": "status", "operator": "eq", "value": "active"},
                {"field": "year", "operator": "gte", "value": 2020}
            ]
        }
    }

    Supported Filter Operators:
    'eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'like'

    JSON Response Body:
    [
        {
            "properties": { ... filtered properties ... },
            "score": 0.85,
            "distance": 0.15,
            "uuid": "..."
        },
        ...
    ]
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        # --- Validate Input ---
        collection_name = data.get("collection_name")
        query_text = data.get("query")
        if not collection_name or not query_text:
            return jsonify({"error": "Missing required fields: 'collection_name' and 'query'"}), 400

        top_k = int(data.get("top_k", 5))
        exclude_fields = data.get("exclude_fields", [])
        if not isinstance(exclude_fields, list):
             return jsonify({"error": "'exclude_fields' must be a list of strings"}), 400

        filters_input = data.get("filters")

        # --- Get Collection ---
        try:
            collection = client.collections.get(collection_name)
        except Exception as e:
            # Check for collection not found error message
            if "Not found: Collection" in str(e) or "doesn't exist" in str(e):
                logger.warning(f"Collection '{collection_name}' not found.")
                return jsonify({"error": f"Collection '{collection_name}' not found"}), 404
            else:
                logger.error(f"Error getting collection '{collection_name}': {str(e)}", exc_info=True)
                return jsonify({"error": "Failed to access collection", "details": str(e)}), 500


        # --- Build Weaviate Filter (if provided) ---
        weaviate_filter = None
        if filters_input and isinstance(filters_input, dict):
            conditions_input = filters_input.get("conditions", [])
            operator_type = filters_input.get("operator", "And").lower()

            if conditions_input and isinstance(conditions_input, list):
                filter_conditions = []
                supported_ops = {
                    "eq": wq.Filter.by_property, # .equal() is applied later
                    "neq": wq.Filter.by_property, # .not_equal() is applied later
                    "gt": wq.Filter.by_property, # .greater_than() is applied later
                    "gte": wq.Filter.by_property, # .greater_or_equal() is applied later
                    "lt": wq.Filter.by_property, # .less_than() is applied later
                    "lte": wq.Filter.by_property, # .less_or_equal() is applied later
                    "like": wq.Filter.by_property # .like() is applied later
                }

                for cond in conditions_input:
                    field = cond.get("field")
                    op = cond.get("operator", "").lower()
                    value = cond.get("value") # Value can be string, number, bool

                    if not field or op not in supported_ops or value is None:
                        logger.warning(f"Skipping invalid filter condition: {cond}")
                        continue

                    # Start building the filter for the property
                    prop_filter = supported_ops[op](field)

                    # Apply the specific comparison method
                    if op == "eq":
                        filter_conditions.append(prop_filter.equal(value))
                    elif op == "neq":
                        filter_conditions.append(prop_filter.not_equal(value))
                    elif op == "gt":
                        filter_conditions.append(prop_filter.greater_than(value))
                    elif op == "gte":
                        filter_conditions.append(prop_filter.greater_or_equal(value))
                    elif op == "lt":
                        filter_conditions.append(prop_filter.less_than(value))
                    elif op == "lte":
                        filter_conditions.append(prop_filter.less_or_equal(value))
                    elif op == "like":
                         if isinstance(value, str):
                             filter_conditions.append(prop_filter.like(value))
                         else:
                             logger.warning(f"'like' operator requires string value, got {type(value)}. Skipping filter: {cond}")


                if filter_conditions:
                    if operator_type == "or":
                        weaviate_filter = wq.Filter.any_of(filter_conditions)
                    else: # Default to AND
                        weaviate_filter = wq.Filter.all_of(filter_conditions)
            else:
                 logger.warning(f"Invalid 'filters' format: {filters_input}")

        # --- Perform Search ---
        logger.info(f"Querying '{collection_name}' for '{query_text}' (top_k={top_k}, filters={'Yes' if weaviate_filter else 'No'})")
        response = collection.query.near_text(
            query=query_text,
            limit=top_k,
            filters=weaviate_filter,
            # Request metadata including distance
            return_metadata=wq.MetadataQuery(distance=True),
            # Fetch all properties initially, will filter later if needed
            return_properties=None
        )

        # --- Process Results ---
        results = []
        if response and response.objects:
            logger.info(f"Found {len(response.objects)} potential results.")
            for obj in response.objects:
                properties = process_properties(obj.properties) # Serialize properties

                # Filter out excluded fields
                if exclude_fields:
                    filtered_properties = {k: v for k, v in properties.items() if k not in exclude_fields}
                else:
                    filtered_properties = properties

                distance = obj.metadata.distance if obj.metadata and obj.metadata.distance is not None else None
                # Calculate score (assuming cosine distance, score = 1 - distance)
                # Adjust if using a different distance metric where lower is better
                score = (1.0 - distance) if distance is not None else 0.0

                results.append({
                    "properties": filtered_properties,
                    "score": score,
                    "distance": distance,
                    "uuid": str(obj.uuid) # Include the object's UUID
                })
        else:
             logger.info("No results found for the query.")


        return jsonify(results)

    except Exception as e:
        logger.error(f"Error processing query request: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Use a more lightweight check like getting meta information
        meta = client.get_meta()
        if client.is_ready():
             logger.debug("Health check successful.")
             return jsonify({"status": "healthy", "weaviate_version": meta.get('version')}), 200
        else:
             logger.warning("Health check failed: Weaviate client is not ready.")
             return jsonify({"status": "unhealthy", "message": "Weaviate client not ready"}), 503
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return jsonify({"status": "unhealthy", "message": str(e)}), 500

# --- Run Flask App ---
if __name__ == '__main__':
    try:
        # Use a production-ready server like waitress or gunicorn instead of Flask's built-in server
        # For local development/testing, Flask's server is fine:
        app.run(host='0.0.0.0', port=5001, debug=False) # Changed port to 5001
    except Exception as e:
         logger.critical(f"Failed to start Flask application: {e}", exc_info=True)
    finally:
        # Ensure the client connection is closed gracefully
        if client and client.is_connected():
            client.close()
            logger.info("Weaviate client closed.")
