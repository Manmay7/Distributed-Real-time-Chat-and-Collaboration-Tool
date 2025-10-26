from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class LLMRequest(_message.Message):
    __slots__ = ["request_id", "query", "context", "parameters"]
    class ParametersEntry(_message.Message):
        __slots__ = ["key", "value"]
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    query: str
    context: _containers.RepeatedScalarFieldContainer[str]
    parameters: _containers.ScalarMap[str, str]
    def __init__(self, request_id: _Optional[str] = ..., query: _Optional[str] = ..., context: _Optional[_Iterable[str]] = ..., parameters: _Optional[_Mapping[str, str]] = ...) -> None: ...

class LLMResponse(_message.Message):
    __slots__ = ["request_id", "answer", "confidence"]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ANSWER_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    answer: str
    confidence: float
    def __init__(self, request_id: _Optional[str] = ..., answer: _Optional[str] = ..., confidence: _Optional[float] = ...) -> None: ...

class SmartReplyRequest(_message.Message):
    __slots__ = ["request_id", "recent_messages", "user_id"]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    RECENT_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    recent_messages: _containers.RepeatedCompositeFieldContainer[ChatMessage]
    user_id: str
    def __init__(self, request_id: _Optional[str] = ..., recent_messages: _Optional[_Iterable[_Union[ChatMessage, _Mapping]]] = ..., user_id: _Optional[str] = ...) -> None: ...

class ChatMessage(_message.Message):
    __slots__ = ["sender", "content", "timestamp"]
    SENDER_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    sender: str
    content: str
    timestamp: int
    def __init__(self, sender: _Optional[str] = ..., content: _Optional[str] = ..., timestamp: _Optional[int] = ...) -> None: ...

class SmartReplyResponse(_message.Message):
    __slots__ = ["request_id", "suggestions"]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SUGGESTIONS_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    suggestions: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, request_id: _Optional[str] = ..., suggestions: _Optional[_Iterable[str]] = ...) -> None: ...

class SummarizeRequest(_message.Message):
    __slots__ = ["request_id", "messages", "max_length"]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    MAX_LENGTH_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    messages: _containers.RepeatedCompositeFieldContainer[ChatMessage]
    max_length: int
    def __init__(self, request_id: _Optional[str] = ..., messages: _Optional[_Iterable[_Union[ChatMessage, _Mapping]]] = ..., max_length: _Optional[int] = ...) -> None: ...

class SummarizeResponse(_message.Message):
    __slots__ = ["request_id", "summary", "key_points"]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    KEY_POINTS_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    summary: str
    key_points: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, request_id: _Optional[str] = ..., summary: _Optional[str] = ..., key_points: _Optional[_Iterable[str]] = ...) -> None: ...

class ContextRequest(_message.Message):
    __slots__ = ["request_id", "context", "current_input"]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    CURRENT_INPUT_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    context: _containers.RepeatedCompositeFieldContainer[ChatMessage]
    current_input: str
    def __init__(self, request_id: _Optional[str] = ..., context: _Optional[_Iterable[_Union[ChatMessage, _Mapping]]] = ..., current_input: _Optional[str] = ...) -> None: ...

class SuggestionsResponse(_message.Message):
    __slots__ = ["request_id", "suggestions", "topics"]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SUGGESTIONS_FIELD_NUMBER: _ClassVar[int]
    TOPICS_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    suggestions: _containers.RepeatedScalarFieldContainer[str]
    topics: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, request_id: _Optional[str] = ..., suggestions: _Optional[_Iterable[str]] = ..., topics: _Optional[_Iterable[str]] = ...) -> None: ...
