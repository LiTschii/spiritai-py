# SpiritAI Python API

A Flask-based REST API for interacting with Weaviate vector database, designed to provide semantic search capabilities across personal data collections.

## Overview

This API serves as a lightweight wrapper around the Weaviate Python client, exposing key vector search functionality through RESTful endpoints. It's specifically designed to work with personal data collections like diary entries, message histories, and instant thoughts.

## Features

- **Collection Listing**: Get all available collections in the Weaviate instance
- **Semantic Search**: Perform natural language queries against vector embeddings
- **Filtering**: Apply structured filters to narrow down search results
- **Health Monitoring**: Check the connection status to Weaviate

## API Endpoints

### GET `/collections`

Lists all available collections in the Weaviate instance.

**Response:**
```json
{
  "collections": ["Collection1", "Collection2", "Collection3"]
}
```

### POST `/query`

Performs a semantic search on a specified collection.

**Request Body:**
```json
{
  "collection_name": "Your_Collection",  
  "query": "Your search query text",    
  "top_k": 10,                          
  "exclude_fields": ["field1", "field2"],
  "filters": {                          
    "operator": "And",                
    "conditions": [
      {"field": "status", "operator": "eq", "value": "active"},
      {"field": "year", "operator": "gte", "value": 2020}
    ]
  }
}
```

**Parameters:**
- `collection_name` (required): Name of the collection to search
- `query` (required): Natural language query text
- `top_k` (optional): Number of results to return (default: 5)
- `exclude_fields` (optional): Array of field names to exclude from results
- `filters` (optional): Structured filter object with operator and conditions

**Supported Filter Operators:**
- `eq`: Equal to
- `neq`: Not equal to
- `gt`: Greater than
- `gte`: Greater than or equal to
- `lt`: Less than
- `lte`: Less than or equal to
- `like`: Text matching (wildcards supported)

**Response:**
```json
[
  {
    "properties": {
      "field1": "value1",
      "field2": "value2"
    },
    "score": 0.85,
    "distance": 0.15,
    "uuid": "uuid-string"
  }
]
```

### GET `/health`

Checks the health status of the API and Weaviate connection.

**Response:**
```json
{
  "status": "healthy",
  "weaviate_version": "1.30.0"
}
```

## Setup

1. Ensure you have Python 3.8+ installed
2. Install required packages:
   ```
   pip install flask weaviate-client python-dotenv
   ```
3. Configure your Weaviate connection in a `.env` file:
   ```
   PASSWORD=your_weaviate_api_key
   ```
4. Run the application:
   ```
   python claude-api.py
   ```

## Error Handling

The API returns appropriate HTTP status codes:
- `200`: Success
- `400`: Invalid request (missing parameters, etc.)
- `404`: Collection not found
- `500`: Server or database error

## Implementation Details

- Built with Flask for the web server
- Uses the Weaviate Python client for vector database operations
- Includes serialization logic for complex data types
- Implements comprehensive logging for debugging