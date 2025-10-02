# Interactions

This document is a sketch of the interactions between the frontend and backend of the system.

## CRUD Endpoints

Update the ideas and documents in the database directly, from the frontend.

Document:

Sub router for each document type (PRD, Idea, etc.):

## Agent Endpoints

Chat with the agent, with the ability to generate PRDs and documents.

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Database
    participant Agent

    User->>Frontend: Send message
    Frontend->>Backend: Send message
    Backend->>Agent: Send message
    Agent->>Agent: Process message
    opt Document Generation
        Agent->>Backend: Generate Document
        Backend->>Database: Store Document
    end
    Backend->>Frontend: Send response (with message and/or document)
    Frontend->>User: Display response
```
