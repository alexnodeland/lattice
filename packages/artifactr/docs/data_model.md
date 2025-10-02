# Data Model

## Main Objects

- `User`: Represents a user in the system.
- `Idea`: Represents an idea submitted by a user.
- `PRD`: Represents a Product Requirements Document associated with an idea.
- `Document`: Represents a document associated with a PRD.

```mermaid
graph TD
    U["User"]
    I["Idea"]
    P["PRD"]
    D["Document"]
    T["Thread"]

    I -->|"is associated with"| U
    D -->|"is associated with"| I
    P -->|"is a"| D
    T -->|"is about an"| I
    T -->|"operates on"| D
    T -->|"is associated with"| U
```
