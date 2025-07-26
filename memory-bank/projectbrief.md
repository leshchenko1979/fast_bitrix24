# Project Brief: fast_bitrix24

## Project Overview
`fast_bitrix24` is a high-performance Python API wrapper for Bitrix24 REST API that provides fast data exchange capabilities with thousands of elements per second.

## Core Requirements

### Primary Goals
1. **High-Speed Data Exchange**: Achieve thousands of elements per second on large lists
2. **Automatic Request Batching**: Reduce required server requests by packaging them into batches
3. **Parallel Processing**: Send batches to server in parallel, not sequentially
4. **Advanced Pagination Strategies**: Accelerate data extraction by orders of magnitude
5. **Server Failure Prevention**: Respect all Bitrix24 rate limiting policies
6. **Automatic Throttling**: Reduce speed automatically when server returns errors
7. **Code Convenience**: High-level list methods to reduce required code to one line
8. **Parameter Validation**: Check request parameters for correctness to ease debugging
9. **Progress Visualization**: Automatic progress bars with tqdm showing processed elements and time
10. **OAuth Authorization**: Track token expiration and auto-refresh for application work
11. **Dual Client Support**: Both synchronous and asynchronous clients
12. **Enterprise Optimization**: Support for higher request speeds on Enterprise accounts

### Technical Requirements
- **Language**: Python
- **Dependencies**: aiohttp, tqdm, beartype, icontract
- **Architecture**: Async-first with sync wrapper
- **Rate Limiting**: Respect Bitrix24's Leaky Bucket and Sliding Window policies
- **Error Handling**: Comprehensive exception handling for HTTP and runtime errors
- **Logging**: Configurable logging for request/response debugging
- **SSL Support**: Configurable SSL certificate verification
- **Batch Processing**: Automatic batching of up to 50 requests per batch
- **Pagination Handling**: Automatic handling of paginated responses
- **Parameter Validation**: Pre-request validation of common parameters

### User Experience Goals
- **One-Line Operations**: Most operations should require only one line of code
- **Intuitive API**: Parameters should match Bitrix24 REST API documentation exactly
- **Progress Feedback**: Users should see real-time progress of long operations
- **Error Clarity**: Clear error messages that help with debugging
- **Flexibility**: Support for both simple and complex use cases
- **Performance**: Noticeable speed improvements over manual API calls

### Success Metrics
- **Speed**: Thousands of elements per second on large datasets
- **Reliability**: No server failures due to rate limit violations
- **Adoption**: Used by major companies (e.g., Yandex)
- **Code Reduction**: Significant reduction in boilerplate code
- **Error Reduction**: Fewer API-related errors due to validation

## Project Scope
- **In Scope**: Bitrix24 REST API wrapper with high performance and convenience features
- **Out of Scope**: Direct database access, UI components, other CRM integrations
- **Future Considerations**: Support for additional Bitrix24 features as they become available

## Target Users
- **Primary**: Python developers working with Bitrix24
- **Secondary**: Data analysts, automation engineers, system integrators
- **Enterprise**: Companies with Bitrix24 Enterprise accounts requiring higher throughput
