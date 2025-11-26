import uuid
from threading import Lock
from typing import Dict, Set, Optional, List
from dataclasses import dataclass

# Thread-safe connection tracking
@dataclass(frozen=True)
class ConnectionInfo:
    """Information about an active connection"""
    connection_id: str
    topic_name: str

_connections: Dict[str, Set[ConnectionInfo]] = {}
_lock = Lock()
MAX_CONNECTIONS_PER_USER = 3


def register_connection(user_id: str, topic_name: str) -> tuple[bool, str]:
    """
    Register a new connection for a user.
    Returns (success, connection_id) tuple.
    If limit reached, returns (False, "").
    """
    connection_id = str(uuid.uuid4())
    
    with _lock:
        if user_id not in _connections:
            _connections[user_id] = set()
        
        if len(_connections[user_id]) >= MAX_CONNECTIONS_PER_USER:
            return (False, "")
        
        connection_info = ConnectionInfo(
            connection_id=connection_id,
            topic_name=topic_name
        )
        _connections[user_id].add(connection_info)
        return (True, connection_id)


def unregister_connection(user_id: str, connection_id: str) -> None:
    """Unregister a connection for a user"""
    with _lock:
        if user_id in _connections:
            # Find and remove the connection with matching connection_id
            _connections[user_id] = {
                conn for conn in _connections[user_id]
                if conn.connection_id != connection_id
            }
            if len(_connections[user_id]) == 0:
                del _connections[user_id]


def get_all_active_connections() -> Dict[str, List[dict]]:
    """
    Get all active connections grouped by user.
    Returns a dictionary mapping user_id to a list of connection info dicts.
    """
    with _lock:
        result = {}
        for user_id, connections in _connections.items():
            result[user_id] = [
                {
                    "connection_id": conn.connection_id,
                    "topic_name": conn.topic_name
                }
                for conn in connections
            ]
        return result

