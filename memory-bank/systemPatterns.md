# System Patterns: fast_bitrix24

## Architecture Overview

### Core Architecture Pattern: Async-First with Sync Wrapper
The system follows an async-first architecture where the core functionality is implemented in `BitrixAsync`, and `Bitrix` provides a synchronous wrapper using `asyncio.run()`.

```
Bitrix (Sync Wrapper)
    ↓ (decorates with sync wrapper)
BitrixAsync (Core Implementation)
    ↓ (uses)
ServerRequestHandler (Request Management)
    ↓ (uses)
Throttle (Rate Limiting)
```

### Component Architecture

#### 1. Main Client Classes
- **`BitrixAsync`**: Core async implementation with all API methods
- **`Bitrix`**: Synchronous wrapper that delegates to `BitrixAsync`
- **`ServerRequestHandler`**: Manages HTTP requests and responses
- **`Throttle`**: Implements rate limiting and throttling logic

#### 2. Request Processing Pipeline
```
User Request → Parameter Validation → Request Creation → Batching →
Parallel Execution → Response Processing → Error Handling → Result
```

#### 3. User Request Classes
- **`GetAllUserRequest`**: Handles paginated data retrieval
- **`GetByIDUserRequest`**: Handles ID-based data retrieval
- **`CallUserRequest`**: Handles batch operations
- **`RawCallUserRequest`**: Handles raw API calls
- **`ListAndGetUserRequest`**: Handles list-then-get operations

## Key Technical Decisions

### 1. Async-First Design
**Decision**: Use async/await as the primary programming model
**Rationale**:
- Better performance for I/O-bound operations
- Natural fit for HTTP requests
- Enables true parallelism
- Future-proof for modern Python development

**Implementation**: Core functionality in `BitrixAsync`, sync wrapper in `Bitrix`

### 2. Request Batching Strategy
**Decision**: Automatic batching of up to 50 requests per batch
**Rationale**:
- Reduces HTTP overhead
- Improves throughput
- Balances batch size with error handling granularity
- Respects Bitrix24's batch limitations

**Implementation**: `batch_size` parameter, automatic batching in request handlers

### 3. Rate Limiting Implementation
**Decision**: Dual rate limiting (Leaky Bucket + Sliding Window)
**Rationale**:
- Complies with Bitrix24's official policies
- Prevents server failures
- Enables adaptive throttling
- Supports Enterprise account optimizations

**Implementation**: `Throttle` class with configurable parameters

### 4. Error Handling Strategy
**Decision**: Comprehensive error handling with automatic recovery
**Rationale**:
- Improves reliability
- Provides clear error messages
- Enables automatic throttling on errors
- Maintains user experience during failures

**Implementation**: Exception hierarchy, automatic throttling, detailed logging

### 5. Parameter Validation
**Decision**: Pre-request parameter validation
**Rationale**:
- Catches errors early
- Improves debugging experience
- Reduces server load from invalid requests
- Provides clear error messages

**Implementation**: Type hints, `beartype` decorators, custom validation logic

## Design Patterns

### 1. Decorator Pattern
**Usage**: Method decoration for logging, validation, and error handling
```python
@log
@beartype
async def get_all(self, method: str, params: dict = None):
```

### 2. Context Manager Pattern
**Usage**: `slow()` context manager for temporary speed reduction
```python
with bx.slow():
    results = bx.call('crm.lead.add', tasks)
```

### 3. Strategy Pattern
**Usage**: Different request strategies for different operation types
- `GetAllUserRequest`: Pagination strategy
- `GetByIDUserRequest`: ID-based strategy
- `CallUserRequest`: Batch strategy

### 4. Factory Pattern
**Usage**: Request creation based on operation type
```python
# Request creation based on method and parameters
request = self._create_request(method, params)
```

### 5. Observer Pattern
**Usage**: Progress tracking with tqdm
```python
# Progress bar updates during request execution
with tqdm(total=total_items) as pbar:
    # Update progress as requests complete
```

## Component Relationships

### Core Dependencies
```
fast_bitrix24/
├── __init__.py (exports Bitrix, BitrixAsync)
├── bitrix.py (main client classes)
├── srh.py (ServerRequestHandler)
├── throttle.py (rate limiting)
├── user_request.py (request strategies)
├── server_response.py (response parsing)
├── logger.py (logging utilities)
├── mult_request.py (parallel request handling)
└── utils.py (utility functions)
```

### Request Flow
1. **User calls method** → `Bitrix`/`BitrixAsync`
2. **Parameter validation** → Type checking and validation
3. **Request creation** → Appropriate `UserRequest` class
4. **Batching** → Group requests into batches
5. **Parallel execution** → `ServerRequestHandler`
6. **Rate limiting** → `Throttle` class
7. **Response processing** → `ServerResponseParser`
8. **Error handling** → Exception handling and recovery
9. **Result return** → Processed data to user

### Data Flow
```
User Input → Validation → Request Objects → Batches →
HTTP Requests → Responses → Parsing → Error Handling →
Progress Updates → Final Results
```

## Critical Implementation Paths

### 1. High-Performance Data Retrieval
**Path**: `get_all()` → `GetAllUserRequest` → Parallel batching → `ServerRequestHandler`
**Key Features**:
- Automatic pagination handling
- Parallel batch execution
- Progress tracking
- Error recovery

### 2. Batch Operations
**Path**: `call()` → `CallUserRequest` → Batching → Parallel execution
**Key Features**:
- Automatic request batching
- Parallel execution
- Error handling per request
- Result sorting

### 3. Rate Limiting
**Path**: All requests → `Throttle` → HTTP execution
**Key Features**:
- Leaky Bucket implementation
- Sliding Window tracking
- Adaptive throttling
- Enterprise optimizations

### 4. Error Recovery
**Path**: Error detection → Throttling adjustment → Retry logic
**Key Features**:
- Automatic speed reduction
- Error categorization
- Recovery strategies
- User notification

## Performance Optimizations

### 1. Parallel Execution
- Multiple batches sent concurrently
- Non-blocking I/O operations
- Efficient resource utilization

### 2. Intelligent Batching
- Optimal batch sizes (50 requests)
- Request grouping by type
- Error isolation per batch

### 3. Memory Management
- Streaming response processing
- Efficient data structures
- Garbage collection optimization

### 4. Network Optimization
- Connection pooling
- Request compression
- SSL session reuse

## Security Considerations

### 1. Authentication
- OAuth token management
- Automatic token refresh
- Secure token storage

### 2. SSL/TLS
- Configurable SSL verification
- Certificate validation
- Secure connection handling

### 3. Rate Limiting
- Prevents server overload
- Respects API limits
- Adaptive throttling

## Testing Strategy

### 1. Unit Testing
- Individual component testing
- Mock HTTP responses
- Parameter validation testing

### 2. Integration Testing
- Real API endpoint testing
- Error scenario testing
- Performance testing

### 3. Performance Testing
- Speed benchmarks
- Memory usage testing
- Concurrent request testing
