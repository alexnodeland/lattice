# Agent API Documentation

This document outlines the API for interacting with the agent-based backend services, focusing on agent and WebSocket routes.

## Overview

The agent API provides two primary transport methods for real-time communication:

1. **HTTP Streaming** - Server-Sent Events (SSE) via HTTP streaming responses
2. **WebSocket** - Bidirectional communication via WebSocket protocol

Both methods use a consistent event-based message format for structured data exchange.

## Common Event Structure

All events share a common base structure:

```json
{
  "timestamp": 1639380000.123,
  "metadata": {},
  "type": "event_type"
}
```

- `timestamp`: Float representing the Unix time when the event was created
- `metadata`: Optional dictionary for additional context
- `type`: Discriminator field identifying the event type

## Transport Methods

### 1. HTTP Streaming API

The streaming API delivers events using Server-Sent Events (SSE) format.

#### Endpoint

```text
POST /agent/{thread_id}
```

#### Request

```json
{
  "message": "Your message to the agent"
}
```

#### Response

A Server-Sent Events stream with `Content-Type: text/event-stream`. Each event is formatted as `data: <json>\n\n`. The stream ends with a `DoneEvent`.

**Example:**

```http
POST /agent/123
Content-Type: application/json

{
  "message": "Tell me about quantum computing"
}

HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"timestamp": 1639380000.123, "metadata": {}, "type": "system", "content": "Processing your request"}

data: {"timestamp": 1639380000.456, "metadata": {}, "type": "token", "content": "Quantum"}

data: {"timestamp": 1639380000.789, "metadata": {}, "type": "token", "content": " computing"}

data: {"timestamp": 1639380001.012, "metadata": {}, "type": "done"}

```

#### Client Implementation

**JavaScript (Browser):**
```javascript
// Using native EventSource API
const eventSource = new EventSource('/agent/123');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
  
  if (data.type === 'done') {
    eventSource.close();
  }
};

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
};
```

**Python:**
```python
import requests
import json

response = requests.post('/agent/123', 
                        json={"message": "Hello"}, 
                        stream=True)

for line in response.iter_lines():
    if line.startswith(b'data: '):
        json_data = line[6:]  # Remove 'data: ' prefix
        event = json.loads(json_data)
        print(f"Received: {event}")
        
        if event.get('type') == 'done':
            break
```

### 2. WebSocket API

The WebSocket API provides bidirectional communication with more robust connection management.

#### Connection

```text
WebSocket: /ws/{thread_id}
```

Query Parameters:

- `since`: Optional timestamp to receive events since a specific time

#### Handshake

1. Client connects to WebSocket endpoint
2. Server accepts connection
3. Client sends `HelloEvent`
4. Server validates and responds with `SystemEvent`
5. Connection is established

**Example:**

```text
// Client initiates connection
GET /ws/123e4567-e89b-12d3-a456-426614174000?since=1639380000.123

// After connection established, client sends:
{"type": "hello", "protocol_version": "1.0", "timestamp": 1639380000.123, "metadata": {}}

// Server responds:
{"type": "system", "content": "Protocol negotiated: 1.0", "timestamp": 1639380000.456, "metadata": {}}
```

## Event Types

### Outbound Events (Server to Client)

#### SystemEvent

System-level messages about the overall process.

```json
{
  "type": "system",
  "content": "Processing your request",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### TokenEvent

Individual tokens received from the LLM.

```json
{
  "type": "token",
  "content": "Hello",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### TaskEvent

Updates from concurrent background tasks.

```json
{
  "type": "task",
  "content": "Searching for information",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### ErrorEvent

Error messages when something goes wrong.

```json
{
  "type": "error",
  "content": "Failed to process request",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### MessageFormatEvent

Formatting instructions for UI rendering with opening/closing tags support.

```json
{
  "type": "message_format",
  "content": "Thinking about this...",
  "format": "thinking",
  "is_opening": true,
  "identifier": "1639380000123456789",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### AgentActionEvent

Tool usage by the agent.

```json
{
  "type": "agent_action",
  "content": "Searching the web",
  "tool": "web_search",
  "inputs": {"query": "quantum computing"},
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### DocumentEvent

Document content updates.

```json
{
  "type": "document",
  "content": "# Document Title\n\nContent here",
  "document_id": "doc-123",
  "document_type": "generic",
  "document_data": null,
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### StructuredEvent

Structured data events for streaming typed objects.

```json
{
  "type": "structured",
  "data_type": "document.generic",
  "data": {"title": "Document", "content": "Content"},
  "is_partial": true,
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### DoneEvent

Indicates the end of the stream.

```json
{
  "type": "done",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

### Inbound Events (Client to Server)

#### HelloEvent

Sent by client to identify the connection.

```json
{
  "type": "hello",
  "protocol_version": "1.0",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### ClientMessageEvent

Client message to send text to the server.

```json
{
  "type": "message",
  "content": "Tell me about quantum computing",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

#### StopEvent

Sent by client to stop the current processing.

```json
{
  "type": "stop",
  "reason": "User cancelled",
  "timestamp": 1639380000.123,
  "metadata": {}
}
```

## WebSocket-Specific Features

### Heartbeat

The WebSocket connection uses a heartbeat mechanism to keep the connection alive and detect disconnects:

- The server expects the client to respond to pings within a configured timeout
- If no response is received, the server closes the connection
- The heartbeat interval is defined by the server configuration

### History Replay

The WebSocket API supports retrieving past events:

- Connect with the `since` parameter set to a timestamp
- The server will send all events that occurred after that timestamp
- Useful for reconnecting after a disconnection or for catching up on missed events

### Room Broadcasting

Multiple clients can connect to the same thread:

- All clients connected to the same thread ID receive the same events
- Enables collaborative scenarios with multiple observers

## Error Handling

### HTTP Streaming API Errors

HTTP status codes are used to indicate errors:

- 404: Thread not found
- 500: Internal server error

### WebSocket API Errors

WebSocket close codes are used to indicate errors:

- 1000: Normal closure
- 1001: Going away
- 1002: Protocol error
- 1003: Unsupported data
- 1006: Abnormal closure
- 1011: Internal server error

## SSE vs WebSocket Comparison

| Feature | SSE (HTTP Streaming) | WebSocket |
|---------|---------------------|-----------|
| **Browser Support** | Native `EventSource` | Native `WebSocket` |
| **Reconnection** | Automatic | Manual |
| **Bidirectional** | No (server → client) | Yes |
| **Complexity** | Simple | Moderate |
| **Firewall/Proxy** | Better compatibility | May have issues |
| **Use Case** | Real-time updates | Interactive chat |

Choose SSE for simple real-time updates, WebSocket for interactive bidirectional communication.
