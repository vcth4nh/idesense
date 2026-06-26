package com.github.vcth4nh.idesense.exceptions

import com.github.vcth4nh.idesense.server.models.JsonRpcErrorCodes

sealed class McpException(
    message: String,
    val errorCode: Int,
    val errorType: String
) : Exception(message)

class ParseErrorException(message: String) :
    McpException(message, JsonRpcErrorCodes.PARSE_ERROR, "parse_error")

class InvalidRequestException(message: String) :
    McpException(message, JsonRpcErrorCodes.INVALID_REQUEST, "invalid_request")

class MethodNotFoundException(method: String) :
    McpException("Method not found: $method", JsonRpcErrorCodes.METHOD_NOT_FOUND, "method_not_found")

class InvalidParamsException(message: String) :
    McpException(message, JsonRpcErrorCodes.INVALID_PARAMS, "invalid_params")

class InternalErrorException(message: String) :
    McpException(message, JsonRpcErrorCodes.INTERNAL_ERROR, "internal_error")

class IndexNotReadyException(message: String) :
    McpException(message, JsonRpcErrorCodes.INDEX_NOT_READY, "index_not_ready")

class FileNotFoundException(path: String) :
    McpException("File not found: $path", JsonRpcErrorCodes.FILE_NOT_FOUND, "file_not_found")

class SymbolNotFoundException(message: String) :
    McpException(message, JsonRpcErrorCodes.SYMBOL_NOT_FOUND, "symbol_not_found")

class RefactoringConflictException(message: String) :
    McpException(message, JsonRpcErrorCodes.REFACTORING_CONFLICT, "refactoring_conflict")
