"""
Structured JSON logging for journald capture.
Outputs one JSON object per line to stdout/stderr.
"""
import json
import sys
from datetime import datetime, timezone
from typing import Optional
import uuid


class StructuredLogger:
    """Logger that outputs structured JSON logs to stdout/stderr"""
    
    SERVICE = "api"
    
    def _log(
        self,
        level: str,
        event: str,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        path: Optional[str] = None,
        method: Optional[str] = None,
        topic_name: Optional[str] = None,
        direction: Optional[str] = None,
        bytes: Optional[int] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
        email: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        """Internal method to write structured log entry"""
        # Generate request_id if not provided
        if request_id is None:
            request_id = str(uuid.uuid4())
        
        # Build log entry
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": level,
            "service": self.SERVICE,
            "request_id": request_id,
            "event": event
        }
        
        # Add optional fields
        if user_id is not None:
            log_entry["user_id"] = user_id
        if path is not None:
            log_entry["path"] = path
        if method is not None:
            log_entry["method"] = method
        if topic_name is not None:
            log_entry["topic_name"] = topic_name
        if direction is not None:
            log_entry["direction"] = direction
        if bytes is not None:
            log_entry["bytes"] = bytes
        if status is not None:
            log_entry["status"] = status
        if error is not None:
            log_entry["error"] = error
        if email is not None:
            log_entry["email"] = email
        if reason is not None:
            log_entry["reason"] = reason
        
        # Add any additional kwargs
        log_entry.update(kwargs)
        
        # Serialize to JSON
        log_line = json.dumps(log_entry, ensure_ascii=False)
        
        # Write to stdout for INFO, stderr for WARN/ERROR
        if level == "INFO":
            print(log_line, file=sys.stdout, flush=True)
        else:
            print(log_line, file=sys.stderr, flush=True)
    
    def log_auth(
        self,
        event: str,
        status: str,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        path: Optional[str] = None,
        method: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Log authentication events (signup, login)"""
        level = "INFO" if status == "ok" else "WARN"
        self._log(
            level=level,
            event=event,
            request_id=request_id,
            user_id=user_id,
            email=email,
            path=path,
            method=method,
            status=status,
            error=error
        )
    
    def log_publish(
        self,
        user_id: Optional[str],
        topic_name: str,
        bytes: int,
        status: str,
        request_id: Optional[str] = None,
        path: Optional[str] = None,
        method: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Log publish events"""
        level = "INFO" if status == "ok" else ("WARN" if status == "quota_exceeded" else "ERROR")
        self._log(
            level=level,
            event="publish",
            request_id=request_id,
            user_id=user_id,
            path=path,
            method=method,
            topic_name=topic_name,
            direction="publish",
            bytes=bytes,
            status=status,
            error=error
        )
    
    def log_stream(
        self,
        event: str,
        user_id: Optional[str],
        topic_name: str,
        request_id: Optional[str] = None,
        path: Optional[str] = None,
        method: Optional[str] = None,
        reason: Optional[str] = None,
        error: Optional[str] = None,
        status: Optional[str] = None
    ):
        """Log stream events (start, end, errors)"""
        # Determine level based on event and status
        if event == "stream" and status == "start":
            level = "INFO"
        elif event == "stream" and status == "end":
            level = "INFO"
        elif status == "quota_exceeded":
            level = "WARN"
        else:
            level = "ERROR"
        
        self._log(
            level=level,
            event=event,
            request_id=request_id,
            user_id=user_id,
            path=path,
            method=method,
            topic_name=topic_name,
            direction="stream-out",
            status=status,
            reason=reason,
            error=error
        )
    
    def log_internal(
        self,
        level: str,
        event: str,
        request_id: Optional[str] = None,
        path: Optional[str] = None,
        method: Optional[str] = None,
        error: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ):
        """Log internal events (database errors, Kafka connection issues, etc.)"""
        self._log(
            level=level,
            event=event,
            request_id=request_id,
            user_id=user_id,
            path=path,
            method=method,
            status="error" if level in ["WARN", "ERROR"] else "ok",
            error=error,
            **kwargs
        )


# Global logger instance
logger = StructuredLogger()

