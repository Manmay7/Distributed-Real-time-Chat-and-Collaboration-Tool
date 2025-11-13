import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StatusResponse(_message.Message):
    __slots__ = ("success", "message", "code", "error", "leader_address")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    LEADER_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    code: int
    error: str
    leader_address: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., code: _Optional[int] = ..., error: _Optional[str] = ..., leader_address: _Optional[str] = ...) -> None: ...

class LoginRequest(_message.Message):
    __slots__ = ("username", "password")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    username: str
    password: str
    def __init__(self, username: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class LoginResponse(_message.Message):
    __slots__ = ("success", "token", "message", "user_info")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    USER_INFO_FIELD_NUMBER: _ClassVar[int]
    success: bool
    token: str
    message: str
    user_info: UserInfo
    def __init__(self, success: bool = ..., token: _Optional[str] = ..., message: _Optional[str] = ..., user_info: _Optional[_Union[UserInfo, _Mapping]] = ...) -> None: ...

class SignupRequest(_message.Message):
    __slots__ = ("username", "password", "email", "display_name")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    username: str
    password: str
    email: str
    display_name: str
    def __init__(self, username: _Optional[str] = ..., password: _Optional[str] = ..., email: _Optional[str] = ..., display_name: _Optional[str] = ...) -> None: ...

class SignupResponse(_message.Message):
    __slots__ = ("success", "message", "code", "user_info", "error", "leader_address")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    USER_INFO_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    LEADER_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    code: int
    user_info: UserInfo
    error: str
    leader_address: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., code: _Optional[int] = ..., user_info: _Optional[_Union[UserInfo, _Mapping]] = ..., error: _Optional[str] = ..., leader_address: _Optional[str] = ...) -> None: ...

class LogoutRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class StreamRequest(_message.Message):
    __slots__ = ("token", "channel_ids", "include_direct_messages")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_IDS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_DIRECT_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    token: str
    channel_ids: _containers.RepeatedScalarFieldContainer[str]
    include_direct_messages: bool
    def __init__(self, token: _Optional[str] = ..., channel_ids: _Optional[_Iterable[str]] = ..., include_direct_messages: bool = ...) -> None: ...

class MessageEvent(_message.Message):
    __slots__ = ("event_type", "message", "direct_message", "user", "file", "channel_id")
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    DIRECT_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    FILE_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    event_type: str
    message: Message
    direct_message: DirectMessage
    user: UserInfo
    file: FileMetadata
    channel_id: str
    def __init__(self, event_type: _Optional[str] = ..., message: _Optional[_Union[Message, _Mapping]] = ..., direct_message: _Optional[_Union[DirectMessage, _Mapping]] = ..., user: _Optional[_Union[UserInfo, _Mapping]] = ..., file: _Optional[_Union[FileMetadata, _Mapping]] = ..., channel_id: _Optional[str] = ...) -> None: ...

class UserInfo(_message.Message):
    __slots__ = ("user_id", "username", "is_admin", "status", "last_seen", "display_name", "email")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    IS_ADMIN_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    username: str
    is_admin: bool
    status: str
    last_seen: _timestamp_pb2.Timestamp
    display_name: str
    email: str
    def __init__(self, user_id: _Optional[str] = ..., username: _Optional[str] = ..., is_admin: bool = ..., status: _Optional[str] = ..., last_seen: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., display_name: _Optional[str] = ..., email: _Optional[str] = ...) -> None: ...

class GetOnlineUsersRequest(_message.Message):
    __slots__ = ("token", "channel_id")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    token: str
    channel_id: str
    def __init__(self, token: _Optional[str] = ..., channel_id: _Optional[str] = ...) -> None: ...

class UserListResponse(_message.Message):
    __slots__ = ("success", "users")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    USERS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    users: _containers.RepeatedCompositeFieldContainer[UserInfo]
    def __init__(self, success: bool = ..., users: _Optional[_Iterable[_Union[UserInfo, _Mapping]]] = ...) -> None: ...

class UpdatePresenceRequest(_message.Message):
    __slots__ = ("token", "status")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    token: str
    status: str
    def __init__(self, token: _Optional[str] = ..., status: _Optional[str] = ...) -> None: ...

class PostRequest(_message.Message):
    __slots__ = ("token", "type", "channel_id", "content", "file_data", "file_name")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    FILE_DATA_FIELD_NUMBER: _ClassVar[int]
    FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    token: str
    type: str
    channel_id: str
    content: str
    file_data: bytes
    file_name: str
    def __init__(self, token: _Optional[str] = ..., type: _Optional[str] = ..., channel_id: _Optional[str] = ..., content: _Optional[str] = ..., file_data: _Optional[bytes] = ..., file_name: _Optional[str] = ...) -> None: ...

class GetRequest(_message.Message):
    __slots__ = ("token", "type", "channel_id", "limit", "offset")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    token: str
    type: str
    channel_id: str
    limit: int
    offset: int
    def __init__(self, token: _Optional[str] = ..., type: _Optional[str] = ..., channel_id: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class Message(_message.Message):
    __slots__ = ("message_id", "sender_id", "sender_name", "channel_id", "content", "timestamp", "type", "file_url")
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    SENDER_ID_FIELD_NUMBER: _ClassVar[int]
    SENDER_NAME_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    FILE_URL_FIELD_NUMBER: _ClassVar[int]
    message_id: str
    sender_id: str
    sender_name: str
    channel_id: str
    content: str
    timestamp: _timestamp_pb2.Timestamp
    type: str
    file_url: str
    def __init__(self, message_id: _Optional[str] = ..., sender_id: _Optional[str] = ..., sender_name: _Optional[str] = ..., channel_id: _Optional[str] = ..., content: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., type: _Optional[str] = ..., file_url: _Optional[str] = ...) -> None: ...

class GetResponse(_message.Message):
    __slots__ = ("success", "messages", "next_cursor")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    NEXT_CURSOR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    messages: _containers.RepeatedCompositeFieldContainer[Message]
    next_cursor: str
    def __init__(self, success: bool = ..., messages: _Optional[_Iterable[_Union[Message, _Mapping]]] = ..., next_cursor: _Optional[str] = ...) -> None: ...

class DirectMessageRequest(_message.Message):
    __slots__ = ("token", "recipient_username", "content", "file_data", "file_name")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    RECIPIENT_USERNAME_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    FILE_DATA_FIELD_NUMBER: _ClassVar[int]
    FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    token: str
    recipient_username: str
    content: str
    file_data: bytes
    file_name: str
    def __init__(self, token: _Optional[str] = ..., recipient_username: _Optional[str] = ..., content: _Optional[str] = ..., file_data: _Optional[bytes] = ..., file_name: _Optional[str] = ...) -> None: ...

class DirectMessage(_message.Message):
    __slots__ = ("message_id", "sender_id", "sender_name", "recipient_id", "recipient_name", "content", "timestamp", "is_read", "file_url")
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    SENDER_ID_FIELD_NUMBER: _ClassVar[int]
    SENDER_NAME_FIELD_NUMBER: _ClassVar[int]
    RECIPIENT_ID_FIELD_NUMBER: _ClassVar[int]
    RECIPIENT_NAME_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    IS_READ_FIELD_NUMBER: _ClassVar[int]
    FILE_URL_FIELD_NUMBER: _ClassVar[int]
    message_id: str
    sender_id: str
    sender_name: str
    recipient_id: str
    recipient_name: str
    content: str
    timestamp: _timestamp_pb2.Timestamp
    is_read: bool
    file_url: str
    def __init__(self, message_id: _Optional[str] = ..., sender_id: _Optional[str] = ..., sender_name: _Optional[str] = ..., recipient_id: _Optional[str] = ..., recipient_name: _Optional[str] = ..., content: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., is_read: bool = ..., file_url: _Optional[str] = ...) -> None: ...

class GetDirectMessagesRequest(_message.Message):
    __slots__ = ("token", "other_username", "limit", "offset")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    OTHER_USERNAME_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    token: str
    other_username: str
    limit: int
    offset: int
    def __init__(self, token: _Optional[str] = ..., other_username: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class DirectMessageResponse(_message.Message):
    __slots__ = ("success", "messages")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    success: bool
    messages: _containers.RepeatedCompositeFieldContainer[DirectMessage]
    def __init__(self, success: bool = ..., messages: _Optional[_Iterable[_Union[DirectMessage, _Mapping]]] = ...) -> None: ...

class ListConversationsRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class Conversation(_message.Message):
    __slots__ = ("username", "display_name", "unread_count", "last_message")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    UNREAD_COUNT_FIELD_NUMBER: _ClassVar[int]
    LAST_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    username: str
    display_name: str
    unread_count: int
    last_message: DirectMessage
    def __init__(self, username: _Optional[str] = ..., display_name: _Optional[str] = ..., unread_count: _Optional[int] = ..., last_message: _Optional[_Union[DirectMessage, _Mapping]] = ...) -> None: ...

class ConversationsResponse(_message.Message):
    __slots__ = ("success", "conversations")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CONVERSATIONS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    conversations: _containers.RepeatedCompositeFieldContainer[Conversation]
    def __init__(self, success: bool = ..., conversations: _Optional[_Iterable[_Union[Conversation, _Mapping]]] = ...) -> None: ...

class CreateChannelRequest(_message.Message):
    __slots__ = ("token", "channel_name", "description", "is_private")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    IS_PRIVATE_FIELD_NUMBER: _ClassVar[int]
    token: str
    channel_name: str
    description: str
    is_private: bool
    def __init__(self, token: _Optional[str] = ..., channel_name: _Optional[str] = ..., description: _Optional[str] = ..., is_private: bool = ...) -> None: ...

class JoinChannelRequest(_message.Message):
    __slots__ = ("token", "channel_id")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    token: str
    channel_id: str
    def __init__(self, token: _Optional[str] = ..., channel_id: _Optional[str] = ...) -> None: ...

class LeaveChannelRequest(_message.Message):
    __slots__ = ("token", "channel_id")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    token: str
    channel_id: str
    def __init__(self, token: _Optional[str] = ..., channel_id: _Optional[str] = ...) -> None: ...

class GetChannelsRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class Channel(_message.Message):
    __slots__ = ("channel_id", "name", "description", "is_private", "member_count", "created_at")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    IS_PRIVATE_FIELD_NUMBER: _ClassVar[int]
    MEMBER_COUNT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    channel_id: str
    name: str
    description: str
    is_private: bool
    member_count: int
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, channel_id: _Optional[str] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., is_private: bool = ..., member_count: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ChannelListResponse(_message.Message):
    __slots__ = ("success", "channels")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    channels: _containers.RepeatedCompositeFieldContainer[Channel]
    def __init__(self, success: bool = ..., channels: _Optional[_Iterable[_Union[Channel, _Mapping]]] = ...) -> None: ...

class FileUploadRequest(_message.Message):
    __slots__ = ("token", "channel_id", "recipient_username", "file_name", "file_data", "mime_type", "description")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    RECIPIENT_USERNAME_FIELD_NUMBER: _ClassVar[int]
    FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    FILE_DATA_FIELD_NUMBER: _ClassVar[int]
    MIME_TYPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    token: str
    channel_id: str
    recipient_username: str
    file_name: str
    file_data: bytes
    mime_type: str
    description: str
    def __init__(self, token: _Optional[str] = ..., channel_id: _Optional[str] = ..., recipient_username: _Optional[str] = ..., file_name: _Optional[str] = ..., file_data: _Optional[bytes] = ..., mime_type: _Optional[str] = ..., description: _Optional[str] = ...) -> None: ...

class FileUploadResponse(_message.Message):
    __slots__ = ("success", "message", "file_id", "file_url", "error", "leader_address")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    FILE_URL_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    LEADER_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    file_id: str
    file_url: str
    error: str
    leader_address: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., file_id: _Optional[str] = ..., file_url: _Optional[str] = ..., error: _Optional[str] = ..., leader_address: _Optional[str] = ...) -> None: ...

class FileDownloadRequest(_message.Message):
    __slots__ = ("token", "file_id")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    token: str
    file_id: str
    def __init__(self, token: _Optional[str] = ..., file_id: _Optional[str] = ...) -> None: ...

class FileResponse(_message.Message):
    __slots__ = ("success", "file_name", "file_data", "mime_type")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    FILE_DATA_FIELD_NUMBER: _ClassVar[int]
    MIME_TYPE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    file_name: str
    file_data: bytes
    mime_type: str
    def __init__(self, success: bool = ..., file_name: _Optional[str] = ..., file_data: _Optional[bytes] = ..., mime_type: _Optional[str] = ...) -> None: ...

class FileMetadata(_message.Message):
    __slots__ = ("file_id", "file_name", "uploader_name", "file_size", "mime_type", "uploaded_at", "channel_id")
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    UPLOADER_NAME_FIELD_NUMBER: _ClassVar[int]
    FILE_SIZE_FIELD_NUMBER: _ClassVar[int]
    MIME_TYPE_FIELD_NUMBER: _ClassVar[int]
    UPLOADED_AT_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    file_id: str
    file_name: str
    uploader_name: str
    file_size: int
    mime_type: str
    uploaded_at: _timestamp_pb2.Timestamp
    channel_id: str
    def __init__(self, file_id: _Optional[str] = ..., file_name: _Optional[str] = ..., uploader_name: _Optional[str] = ..., file_size: _Optional[int] = ..., mime_type: _Optional[str] = ..., uploaded_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., channel_id: _Optional[str] = ...) -> None: ...

class ListFilesRequest(_message.Message):
    __slots__ = ("token", "channel_id")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    token: str
    channel_id: str
    def __init__(self, token: _Optional[str] = ..., channel_id: _Optional[str] = ...) -> None: ...

class FileListResponse(_message.Message):
    __slots__ = ("success", "files")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    success: bool
    files: _containers.RepeatedCompositeFieldContainer[FileMetadata]
    def __init__(self, success: bool = ..., files: _Optional[_Iterable[_Union[FileMetadata, _Mapping]]] = ...) -> None: ...

class ManageUserRequest(_message.Message):
    __slots__ = ("token", "target_user_id", "action", "reason")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    TARGET_USER_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    token: str
    target_user_id: str
    action: str
    reason: str
    def __init__(self, token: _Optional[str] = ..., target_user_id: _Optional[str] = ..., action: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class ManageChannelRequest(_message.Message):
    __slots__ = ("token", "channel_id", "action", "parameters")
    class ParametersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    token: str
    channel_id: str
    action: str
    parameters: _containers.ScalarMap[str, str]
    def __init__(self, token: _Optional[str] = ..., channel_id: _Optional[str] = ..., action: _Optional[str] = ..., parameters: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ServerInfoRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ServerInfoResponse(_message.Message):
    __slots__ = ("is_leader", "node_id", "state", "current_term", "leader_address", "leader_id", "log_size", "commit_index", "cluster_nodes")
    IS_LEADER_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TERM_FIELD_NUMBER: _ClassVar[int]
    LEADER_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    LOG_SIZE_FIELD_NUMBER: _ClassVar[int]
    COMMIT_INDEX_FIELD_NUMBER: _ClassVar[int]
    CLUSTER_NODES_FIELD_NUMBER: _ClassVar[int]
    is_leader: bool
    node_id: int
    state: str
    current_term: int
    leader_address: str
    leader_id: int
    log_size: int
    commit_index: int
    cluster_nodes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_leader: bool = ..., node_id: _Optional[int] = ..., state: _Optional[str] = ..., current_term: _Optional[int] = ..., leader_address: _Optional[str] = ..., leader_id: _Optional[int] = ..., log_size: _Optional[int] = ..., commit_index: _Optional[int] = ..., cluster_nodes: _Optional[_Iterable[str]] = ...) -> None: ...
