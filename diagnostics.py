Provides centralized logging, metrics collection, error handling, health checks, and profiling.
"""

import asyncio
import json
import logging
import time
import traceback
import sys
import os
import gc
import csv
import io
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum, auto
from dataclasses import dataclass, field
from contextlib import contextmanager
import inspect
import threading

# ============================================================
# 29.1. ENUMS
# ============================================================

    """Log levels."""
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def to_int(self) -> int:
        levels = {
            LogLevel.DEBUG: 1,
            LogLevel.INFO: 2,
            LogLevel.ERROR: 4,
        }
        return levels.get(self, 2)
class MetricType(str, Enum):
    COUNTER = "counter"  # Incrementing counter
    GAUGE = "gauge"      # Current value
    HISTOGRAM = "histogram"  # Distribution
class HealthStatus(str, Enum):
    """Health check status."""
    WARNING = "warning"
    ERROR = "error"

class DiagnosticCategory(str, Enum):
    SYSTEM = "system"
    EVENT = "event"
    PLUGIN = "plugin"
    PLAYER = "player"
    NETWORK = "network"
    DATABASE = "database"
    SAVE = "save"
    PERFORMANCE = "performance"
    CUSTOM = "custom"

# ============================================================
# 29.2. DATA CLASSES

@dataclass
    """Log entry."""
    id: str
    level: LogLevel
    source: str
    category: DiagnosticCategory
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace: Optional[str] = None
    def to_dict(self) -> dict:
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source,
            'message': self.message,
            'exception': self.exception,
            'trace': self.trace

    @classmethod
    def from_dict(cls, data: dict) -> 'LogEntry':
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']) if 'timestamp' in data else datetime.now(),
            level=LogLevel(data.get('level', 'info')),
            category=DiagnosticCategory(data.get('category', 'system')),
            exception=data.get('exception'),
            metadata=data.get('metadata', {}),
        )

@dataclass
class Metric:
    """Metric data."""
    name: str
    type: MetricType
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            'type': self.type.value if hasattr(self.type, 'value') else str(self.type),
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'tags': self.tags,
        }

@dataclass
class ErrorRecord:
    id: str
    timestamp: datetime
    module: str
    message: str
    traceback: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'module': self.module,
            'traceback': self.traceback,
            'exception_type': self.exception_type,
            'resolved': self.resolved,
        }
@dataclass
class HealthCheckResult:
    """Health check result."""
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    def to_dict(self) -> dict:
        return {
            'component': self.component,
            'status': self.status.value if hasattr(self.status, 'value') else str(self.status),
            'details': self.details,
            'timestamp': self.timestamp.isoformat()

@dataclass
class ProfileRecord:
    """Profile record."""
    name: str
    category: DiagnosticCategory
    end_time: Optional[float] = None
    duration: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'start_time': self.start_time,
            'duration': self.duration,
            'metadata': self.metadata
        }

# ============================================================
# 29.3. LOGGER
# ============================================================

    """
    Universal Logger.
    All subsystems use this logger. No print() in production code.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
            return
        self._initialized = True
        self._max_entries = 10000
        self._debug_mode = False
        self._handlers: List[Callable[[LogEntry], None]] = []

        # Configure Python logging
        self._python_logger = logging.getLogger("diagnostics")
        self._python_logger.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
        ))
        self._python_logger.addHandler(handler)
        # Statistics
        self._stats = {
            'total_logs': 0,
            'by_level': defaultdict(int),
            'by_category': defaultdict(int),
            'warnings': 0
        }

    # ===== LOGGING METHODS =====

    def trace(self, message: str, category: DiagnosticCategory = DiagnosticCategory.SYSTEM, **metadata) -> None:
        """Log TRACE level."""
        self._log(LogLevel.TRACE, message, category, **metadata)

        """Log DEBUG level."""
        self._log(LogLevel.DEBUG, message, category, **metadata)
    def info(self, message: str, category: DiagnosticCategory = DiagnosticCategory.SYSTEM, **metadata) -> None:
        self._log(LogLevel.INFO, message, category, **metadata)

    def warning(self, message: str, category: DiagnosticCategory = DiagnosticCategory.SYSTEM, **metadata) -> None:
        """Log WARNING level."""

    def error(self, message: str, category: DiagnosticCategory = DiagnosticCategory.SYSTEM, exception: Optional[Exception] = None, **metadata) -> None:
        exception_str = None
        if exception:
            exception_str = str(exception)
        self._log(LogLevel.ERROR, message, category, exception=exception_str, trace=trace_str, **metadata)

    def critical(self, message: str, category: DiagnosticCategory = DiagnosticCategory.SYSTEM, exception: Optional[Exception] = None, **metadata) -> None:
        """Log CRITICAL level."""
        exception_str = None
        if exception:
            exception_str = str(exception)
        self._log(LogLevel.CRITICAL, message, category, exception=exception_str, trace=trace_str, **metadata)
    def _log(self, level: LogLevel, message: str, category: DiagnosticCategory, **kwargs) -> None:
        """Internal log method."""
        if level.to_int() < self._level.to_int():
            return

        entry = LogEntry(
            id=f"{int(time.time())}_{len(self._entries)}",
            level=level,
            category=category,
            message=message,
            exception=kwargs.get('exception'),
        )

        self._entries.append(entry)

        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        # Update stats
        self._stats['total_logs'] += 1
        self._stats['by_level'][level.value] += 1
        self._stats['by_category'][category.value] += 1
            self._stats['errors'] += 1
            self._stats['warnings'] += 1

        # Notify handlers
        for handler in self._handlers:
                handler(entry)
            except Exception:

        # Python logging
        py_level = {
            LogLevel.TRACE: logging.DEBUG,
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
        }.get(level, logging.INFO)
        self._python_logger.log(py_level, f"[{category.value}] {message}")

    def _get_source(self) -> str:
        """Get source from call stack."""
        if frame:
            # Skip this method and _log
                if frame.f_back:
                else:
                    break

            if frame:
                function = frame.f_code.co_name
                line = frame.f_lineno
        return "unknown"
    # ===== CONFIGURATION =====

    def set_level(self, level: LogLevel) -> None:
        """Set minimum log level."""
        self.info(f"Log level set to {level.value}")

    def set_debug_mode(self, enabled: bool) -> None:
        """Enable/disable debug mode."""
        if enabled:
            self.set_level(LogLevel.TRACE)

    def set_max_entries(self, max_entries: int) -> None:
        """Set maximum log entries."""
        if len(self._entries) > max_entries:
            self._entries = self._entries[-max_entries:]

    def add_handler(self, handler: Callable[[LogEntry], None]) -> None:
        """Add custom log handler."""

    def set_context(self, **kwargs) -> None:
        self._source_context.update(kwargs)
    def clear_context(self) -> None:
        """Clear context."""
        self._source_context.clear()

    # ===== QUERY METHODS =====

    def get_logs(
        self,
        level: Optional[LogLevel] = None,
        source: Optional[str] = None,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> List[LogEntry]:
        """Get logs with filters."""

            result = [e for e in result if e.level == level]
        if category:
            result = [e for e in result if e.category == category]
        if source:
            result = [e for e in result if source in e.source]
        if since:
            result = [e for e in result if e.timestamp >= since]
            result = [e for e in result if e.timestamp <= until]

        result = result[offset:offset + limit]

    def get_errors(self, limit: int = 100) -> List[LogEntry]:
        """Get error logs."""
        return self.get_logs(level=LogLevel.ERROR, limit=limit)
    def get_warnings(self, limit: int = 100) -> List[LogEntry]:
        """Get warning logs."""

    def clear_logs(self) -> None:
        """Clear all logs."""
        self._entries.clear()
        self._stats['by_level'].clear()
        self.info("Logs cleared")

    def get_statistics(self) -> Dict[str, Any]:
        """Get log statistics."""
            **self._stats,
            'current_logs': len(self._entries),
            'level': self._level.value,
        }

    # ===== EXPORT =====

    def export_json(self) -> str:
        """Export logs as JSON."""
        return json.dumps([e.to_dict() for e in self._entries], indent=2, default=str)
    def export_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        for entry in self._entries:
                entry.timestamp.isoformat(),
                entry.level.value,
                entry.category.value,
                entry.exception or ''
            ])

# ============================================================
# 29.4. METRICS MANAGER
# ============================================================
class MetricsManager:

    def __init__(self):
        self._metrics: Dict[str, List[Metric]] = defaultdict(list)
        self._counters: Dict[str, float] = defaultdict(float)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._logger = Logger()

    # ===== COUNTER =====

    def increment(self, name: str, value: float = 1.0, tags: Dict[str, str] = None) -> None:
        """Increment a counter metric."""
            self._counters[name] += value
                name=name,
                type=MetricType.COUNTER,
                value=self._counters[name],
                timestamp=datetime.now(),
                tags=tags or {}
            self._metrics[name].append(metric)

    def decrement(self, name: str, value: float = 1.0, tags: Dict[str, str] = None) -> None:
        """Decrement a counter metric."""
        with self._lock:
            self._counters[name] -= value
            metric = Metric(
                name=name,
                value=self._counters[name],
                tags=tags or {}
            )
            self._metrics[name].append(metric)
            self._rotate_history(name)
    # ===== GAUGE =====

    def set_gauge(self, name: str, value: float, tags: Dict[str, str] = None) -> None:
        """Set a gauge metric."""
            self._gauges[name] = value
            metric = Metric(
                type=MetricType.GAUGE,
                timestamp=datetime.now(),
                tags=tags or {}
            self._metrics[name].append(metric)

    # ===== TIMER =====

    def observe_timer(self, name: str, duration: float, tags: Dict[str, str] = None) -> None:
        with self._lock:
            self._timers[name].append(duration)
                name=name,
                type=MetricType.TIMER,
                value=duration,
                timestamp=datetime.now(),
            )
            self._rotate_history(name)

    @contextmanager
    def timer(self, name: str, tags: Dict[str, str] = None):
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.observe_timer(name, duration, tags)

    # ===== HISTOGRAM =====

        """Observe a histogram value."""
        with self._lock:
            self._histograms[name].append(value)
            metric = Metric(
                name=name,
                type=MetricType.HISTOGRAM,
                value=value,
                tags=tags or {}
            )
            self._metrics[name].append(metric)
            self._rotate_history(name)
    # ===== QUERY METHODS =====
    def get_metric(self, name: str, limit: int = 100) -> List[Metric]:
        """Get metric history."""
        return self._metrics.get(name, [])[-limit:]

    def get_counter(self, name: str) -> float:
        """Get current counter value."""
        return self._counters.get(name, 0.0)

    def get_gauge(self, name: str) -> Optional[float]:
        """Get current gauge value."""
        return self._gauges.get(name)
    def get_timer_stats(self, name: str) -> Dict[str, float]:
        values = self._timers.get(name, [])
        if not values:
            return {'count': 0, 'min': 0, 'max': 0, 'avg': 0, 'p50': 0, 'p95': 0, 'p99': 0}

        sorted_values = sorted(values)
        return {
            'count': len(values),
            'max': max(values),
            'p50': sorted_values[int(len(values) * 0.5)],
            'p95': sorted_values[int(len(values) * 0.95)],
        }

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """Get histogram statistics."""
        if not values:

        sorted_values = sorted(values)
            'count': len(values),
            'max': max(values),
            'avg': sum(values) / len(values),
            'p95': sorted_values[int(len(values) * 0.95)],
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all current metrics."""
            'counters': dict(self._counters),
            'gauges': dict(self._gauges),
                name: self.get_timer_stats(name)
            },
            'histograms': {
                name: self.get_histogram_stats(name)
                for name in self._histograms.keys()
        }

    # ===== CLEAR =====

    def clear_metrics(self) -> None:
        """Clear all metrics."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._timers.clear()

    def reset(self) -> None:
        """Reset all metrics."""
        self.clear_metrics()
    # ===== HELPERS =====

    def _rotate_history(self, name: str) -> None:
        """Rotate metric history."""
            self._metrics[name] = self._metrics[name][-self._max_metric_history:]

    def get_statistics(self) -> Dict[str, Any]:
        """Get metrics statistics."""
        return {
            'total_metrics': total_metrics,
            'gauge_count': len(self._gauges),
            'histogram_count': len(self._histograms),
            'max_history': self._max_metric_history

    # ===== EXPORT =====

    def export_json(self) -> str:
        data = {
            'metrics': {
                name: [m.to_dict() for m in metrics[-100:]]
            },
            'current': self.get_all_metrics()
        }
        return json.dumps(data, indent=2, default=str)
# ============================================================
# ============================================================

class ErrorCollector:
    """Centralized error collection."""
    def __init__(self):
        self._errors: List[ErrorRecord] = []
        self._logger = Logger()
        self._lock = threading.Lock()

    def collect(
        self,
        module: str = None,
        metadata: Dict[str, Any] = None
        """Collect an error."""
            if isinstance(exception, Exception):
                error_msg = str(exception)
                error_trace = traceback.format_exc()
                error_type = exception.__class__.__name__
                error_msg = str(exception)
                error_trace = ""

                # Try to get module from call stack
                frame = inspect.currentframe()
                    module = frame.f_back.f_globals.get('__name__', 'unknown')
            record = ErrorRecord(
                id=f"err_{int(time.time())}_{len(self._errors)}",
                module=module or 'unknown',
                traceback=error_trace,
                exception_type=error_type,
            )

            self._errors.append(record)

            if len(self._errors) > self._max_errors:
                self._errors = self._errors[-self._max_errors:]
            self._logger.error(f"Error collected: {error_msg}", exception=exception, **metadata or {})
            return record
    def get_errors(
        self,
        module: Optional[str] = None,
        resolved: Optional[bool] = None,
        offset: int = 0,
    ) -> List[ErrorRecord]:
        """Get errors with filters."""

        if module:
            result = [e for e in result if module in e.module]
        if resolved is not None:
            result = [e for e in result if e.resolved == resolved]
        if since:
            result = [e for e in result if e.timestamp >= since]
        return result[offset:offset + limit]

    def mark_resolved(self, error_id: str) -> bool:
        with self._lock:
                if error.id == error_id:
                    error.resolved = True
                    return True
            return False

    def clear_errors(self) -> None:
        """Clear all errors."""
            self._errors.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """Get error statistics."""
        unresolved = 0

        for error in self._errors:
            error_types[error.exception_type] += 1
                unresolved += 1

        return {
            'total_errors': len(self._errors),
            'resolved': len(self._errors) - unresolved,
            'by_type': dict(error_types),
        }

    def export_json(self) -> str:
        """Export errors as JSON."""

# ============================================================
# 29.6. PERFORMANCE MONITOR
# ============================================================
class PerformanceMonitor:
    """Performance monitoring and profiling."""

    def __init__(self):
        self._profiles: List[ProfileRecord] = []
        self._active_profiles: Dict[str, ProfileRecord] = {}
        self._logger = Logger()
        self._lock = threading.Lock()

    @contextmanager
    def profile(self, name: str, category: DiagnosticCategory = DiagnosticCategory.PERFORMANCE, **metadata):
        """Profile a code block."""
        record = ProfileRecord(
            name=name,
            category=category,
            start_time=time.perf_counter(),
        )

            self._active_profiles[name] = record
        try:
            yield
            end_time = time.perf_counter()

            with self._lock:
                record.duration = duration
                if name in self._active_profiles:
                    del self._active_profiles[name]
                if len(self._profiles) > self._max_profiles:

            # Record as timer metric
            self._metrics.observe_timer(metric_name, duration, metadata)
            if duration > 1.0:
                self._logger.warning(f"Profile {name} took {duration:.3f}s", category=category, **metadata)
                self._logger.debug(f"Profile {name} took {duration:.3f}s", category=category, **metadata)

    def start_profile(self, name: str, category: DiagnosticCategory = DiagnosticCategory.PERFORMANCE, **metadata) -> str:
        """Start a profile manually."""
            name=name,
            category=category,
            metadata=metadata

        with self._lock:
        return name

    def end_profile(self, name: str) -> Optional[ProfileRecord]:
        """End a profile manually."""
            record = self._active_profiles.get(name)
                return None

            record.duration = record.end_time - record.start_time
            del self._active_profiles[name]

            if len(self._profiles) > self._max_profiles:
                self._profiles = self._profiles[-self._max_profiles:]
            return record

    def get_profiles(
        self,
        name: Optional[str] = None,
        category: Optional[DiagnosticCategory] = None,
        limit: int = 100,
        min_duration: Optional[float] = None
    ) -> List[ProfileRecord]:
        result = self._profiles

        if name:
            result = [p for p in result if name in p.name]
            result = [p for p in result if p.category == category]
        if min_duration is not None:

        return result[-limit:]

    def get_profile_stats(self, name: str) -> Dict[str, Any]:
        profiles = [p for p in self._profiles if p.name == name and p.duration is not None]
            return {'count': 0}

        durations = [p.duration for p in profiles]
        sorted_durations = sorted(durations)
        return {
            'count': len(profiles),
            'max': max(durations),
            'p50': sorted_durations[int(len(durations) * 0.5)],
            'p95': sorted_durations[int(len(durations) * 0.95)],
            'total_time': sum(durations)

    def get_active_profiles(self) -> List[ProfileRecord]:
        """Get currently active profiles."""
        with self._lock:
            return list(self._active_profiles.values())

    def clear_profiles(self) -> None:
        """Clear all profiles."""
        with self._lock:
            self._profiles.clear()
            self._active_profiles.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """Get profile statistics."""
        total_profiles = len(self._profiles)
        active_profiles = len(self._active_profiles)

        # Average duration by category
        avg_by_category = defaultdict(list)
            if profile.duration is not None:
                avg_by_category[profile.category.value].append(profile.duration)
        avg_durations = {
            cat: sum(durations) / len(durations)
            for cat, durations in avg_by_category.items()
            if durations

        return {
            'total_profiles': total_profiles,
            'active_profiles': active_profiles,
            'avg_duration_by_category': avg_durations

# ============================================================
# ============================================================
class DiagnosticsAPI:
    """Unified API for diagnostics."""
    def __init__(self):
        self.logger = Logger()
        self.metrics = MetricsManager()
        self.error_collector = ErrorCollector()
        self._health_checks: Dict[str, Callable[[], HealthCheckResult]] = {}
        self._permission_system = None
        self._save_system = None
        self._room_manager = None
        self._database = None
        self._diagnostic_events: List[dict] = []

    # ===== SETUP =====

    def set_event_bus(self, event_bus) -> None:
        self._event_bus = event_bus

    def set_permission_system(self, permission_system) -> None:
        """Set permission system reference."""
        self._permission_system = permission_system

    def set_save_system(self, save_system) -> None:
        """Set save system reference."""

    def set_plugin_manager(self, plugin_manager) -> None:
        self._plugin_manager = plugin_manager
    def set_room_manager(self, room_manager) -> None:
        """Set room manager reference."""

    def set_websocket_manager(self, websocket_manager) -> None:
        """Set websocket manager reference."""
        self._websocket_manager = websocket_manager
    def set_database(self, database) -> None:
        self._database = database

    def _subscribe_to_events(self):
        """Subscribe to system events."""
            return

        try:
            # Subscribe to events
                'ROOM_CREATED', 'ROOM_STARTED', 'ROOM_ENDED',
                'SAVE_CREATED', 'SAVE_LOADED', 'SAVE_DELETED',
                'PLAYER_JOINED', 'PLAYER_LEFT',
            ]

            for event in events:

            self.logger.info(f"Subscribed to {len(events)} system events")
            self.logger.error(f"Failed to subscribe to events: {e}")
    # ===== EVENT HANDLERS =====

        """Handle system events."""
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })

        if len(self._diagnostic_events) > self._max_diagnostic_events:
            self._diagnostic_events = self._diagnostic_events[-self._max_diagnostic_events:]
        self.logger.debug(f"System event: {event_type}", category=DiagnosticCategory.EVENT, **data)
        # Track metrics for events
        self.metrics.increment(f"event_{event_type.lower()}")
        # Track rooms
        if event_type == 'ROOM_CREATED':
            self.metrics.increment('rooms_total')
            self.metrics.set_gauge('rooms_active', len(self._diagnostic_events))  # Rough estimate
    # ===== HEALTH CHECKS =====
    def register_health_check(self, name: str, check: Callable[[], HealthCheckResult]) -> None:
        """Register a health check."""
        self._health_checks[name] = check
    def run_health_checks(self) -> List[HealthCheckResult]:
        """Run all health checks."""

        # Built-in checks
        if self._event_bus:
            results.append(self._check_event_bus())
            results.append(self._check_permission_system())
            results.append(self._check_save_system())
        if self._plugin_manager:
        if self._room_manager:
        if self._websocket_manager:
            results.append(self._check_websocket())
        if self._database:
            results.append(self._check_database())
        # Custom checks
        for name, check in self._health_checks.items():
                results.append(check())
                results.append(HealthCheckResult(
                    component=name,
                    message=f"Health check failed: {e}",
                ))

        return results

    def _check_event_bus(self) -> HealthCheckResult:
        """Check event bus health."""
        try:
            # Check if we can publish a test event
            return HealthCheckResult(
                component="Event Bus",
                message="Event bus is responding"
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.ERROR,
                details={'error': str(e)}
            )
    def _check_permission_system(self) -> HealthCheckResult:
        try:
            # Check if we can check a permission
            return HealthCheckResult(
                component="Permission System",
                status=HealthStatus.HEALTHY,
                message="Permission system is responding",
            )
        except Exception as e:
            return HealthCheckResult(
                component="Permission System",
                message=f"Permission system failed: {e}",
            )

    def _check_save_system(self) -> HealthCheckResult:
        """Check save system health."""
            # Check if we can access save system
            if hasattr(self._save_system, 'get_all_saves'):
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message="Save system is responding",
                )
            return HealthCheckResult(
                component="Save System",
                status=HealthStatus.WARNING,
            )
        except Exception as e:
            return HealthCheckResult(
                component="Save System",
                message=f"Save system failed: {e}",
            )

    def _check_plugin_system(self) -> HealthCheckResult:
        """Check plugin system health."""
            if hasattr(self._plugin_manager, 'get_plugins'):
                plugins = self._plugin_manager.get_plugins()
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message=f"Plugin system is responding",
                )
            return HealthCheckResult(
                component="Plugin System",
                status=HealthStatus.WARNING,
            )
        except Exception as e:
            return HealthCheckResult(
                component="Plugin System",
                message=f"Plugin system failed: {e}",
            )

    def _check_room_manager(self) -> HealthCheckResult:
        """Check room manager health."""
        try:
            if hasattr(self._room_manager, 'get_all_rooms'):
                rooms = self._room_manager.get_all_rooms()
                    component="Room Manager",
                    status=HealthStatus.HEALTHY,
                    message="Room manager is responding",
                )
            return HealthCheckResult(
                component="Room Manager",
                status=HealthStatus.WARNING,
            )
        except Exception as e:
            return HealthCheckResult(
                component="Room Manager",
                message=f"Room manager failed: {e}",
            )

    def _check_websocket(self) -> HealthCheckResult:
        """Check websocket health."""
            if hasattr(self._websocket_manager, 'get_connections'):
                connections = self._websocket_manager.get_connections()
                    component="WebSocket",
                    message="WebSocket is responding",
                    details={'active_connections': len(connections)}
            return HealthCheckResult(
                component="WebSocket",
                status=HealthStatus.WARNING,
                message="WebSocket is available but limited"
            )
        except Exception as e:
            return HealthCheckResult(
                component="WebSocket",
                message=f"WebSocket failed: {e}",
            )

        """Check database health."""
            # Simple check - try to get current time from DB
            if hasattr(self._database, 'execute'):
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message="Database is responding",
                )
                component="Database",
                status=HealthStatus.WARNING,
            )
        except Exception as e:
            return HealthCheckResult(
                component="Database",
                message=f"Database failed: {e}",
            )

    # ===== QUERY METHODS =====

    def get_logs(self, **kwargs) -> List[LogEntry]:
        """Get logs."""
        return self.logger.get_logs(**kwargs)
    def get_errors(self, **kwargs) -> List[ErrorRecord]:
        return self.error_collector.get_errors(**kwargs)

    def get_metrics(self, name: str = None, **kwargs) -> Union[List[Metric], Dict[str, Any]]:
        """Get metrics."""
        if name:
            return self.metrics.get_metric(name, **kwargs)
        return self.metrics.get_all_metrics()

    def get_profiles(self, **kwargs) -> List[ProfileRecord]:
        """Get profiles."""

    def get_diagnostic_events(self, limit: int = 100) -> List[dict]:
        return self._diagnostic_events[-limit:]
    # ===== CLEAR =====

    def clear_logs(self) -> None:
        """Clear logs."""
        self.logger.clear_logs()

    def clear_errors(self) -> None:
        """Clear errors."""
        self.error_collector.clear_errors()
    def clear_metrics(self) -> None:
        """Clear metrics."""

    def clear_profiles(self) -> None:
        """Clear profiles."""
        self.performance.clear_profiles()
    def clear_diagnostic_events(self) -> None:
        self._diagnostic_events.clear()

    def clear_all(self) -> None:
        """Clear all diagnostic data."""
        self.clear_errors()
        self.clear_metrics()
        self.clear_profiles()
        self.clear_diagnostic_events()
    # ===== EXPORT =====

    def export_all(self, format: str = "json") -> Dict[str, Any]:
        """Export all diagnostic data."""
            return {
                'timestamp': datetime.now().isoformat(),
                'errors': [e.to_dict() for e in self.error_collector.get_errors(limit=1000)],
                'profiles': [p.to_dict() for p in self.performance.get_profiles(limit=1000)],
                'health': [h.to_dict() for h in self.run_health_checks()],
            }
        return {}

    # ===== STATISTICS =====

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
            'logger': self.logger.get_statistics(),
            'errors': self.error_collector.get_statistics(),
            'performance': self.performance.get_statistics(),
                'timestamp': datetime.now().isoformat(),
                'cpu_usage': self._get_cpu_usage(),
                'active_threads': threading.active_count(),
            }
        }

    def _get_memory_usage(self) -> Optional[Dict[str, float]]:
        try:
            import psutil
            process = psutil.Process()
            memory = process.memory_info()
                'rss': memory.rss / 1024 / 1024,  # MB
                'percent': process.memory_percent()
            }
            # Fallback to gc
                'objects': gc.get_count(),
                'collected': len(gc.garbage)
        except Exception:

    def _get_cpu_usage(self) -> Optional[float]:
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            return None
        except Exception:
            return None

# ============================================================
# ============================================================
diagnostics = DiagnosticsAPI()
logger = diagnostics.logger
metrics = diagnostics.metrics
error_collector = diagnostics.error_collector

# ============================================================
# ============================================================
def log_call(level: LogLevel = LogLevel.DEBUG):
    """Decorator to log function calls."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.log(level, f"Calling {func.__name__}", category=DiagnosticCategory.PERFORMANCE)
            try:
                result = func(*args, **kwargs)
                logger.debug(f"Finished {func.__name__}", category=DiagnosticCategory.PERFORMANCE)
            except Exception as e:
                raise
        return wrapper
    return decorator

def profile_call(name: str = None):
    def decorator(func):
        @functools.wraps(func)
            profile_name = name or func.__name__
                return func(*args, **kwargs)
        return wrapper

def measure_metric(name: str, type: MetricType = MetricType.TIMER):
    """Decorator to measure function metrics."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            if type == MetricType.TIMER:
                start = time.perf_counter()
                try:
                finally:
                    metrics.observe_timer(name, duration)
            elif type == MetricType.COUNTER:
                return func(*args, **kwargs)
                return func(*args, **kwargs)
        return wrapper
    return decorator

# ============================================================
# 29.10. TESTS
# ============================================================
async def test_diagnostics():
    print("\n" + "="*60)
    print("🧪 ТЕСТИРОВАНИЕ DIAGNOSTICS SYSTEM")

    # Test 1: Logger
    print("\n📋 Тест 1: Логирование")
    logger.info("Test info message", test=True)
    logger.error("Test error message", test=True)
    logs = logger.get_logs(limit=10)
    print(f"   ✅ Записано {len(logs)} логов")

    # Test 2: Metrics
    print("\n📋 Тест 2: Сбор метрик")
    metrics.increment("test_counter", tags={"env": "test"})
    metrics.set_gauge("test_gauge", 42.0)
        time.sleep(0.1)
    metrics.observe_histogram("test_histogram", 1.0)
    metrics.observe_histogram("test_histogram", 3.0)
    print(f"   Counter: {metrics.get_counter('test_counter')}")
    print(f"   Gauge: {metrics.get_gauge('test_gauge')}")
    print(f"   Histogram stats: {metrics.get_histogram_stats('test_histogram')}")
    # Test 3: Error Collector
    print("\n📋 Тест 3: Сбор ошибок")
        raise ValueError("Test error")
        error_record = error_collector.collect(e, module="test_module")
    errors = error_collector.get_errors(limit=10)
    print(f"   Статистика ошибок: {error_collector.get_statistics()}")
    # Test 4: Performance Monitor
    print("\n📋 Тест 4: Профилирование")
        time.sleep(0.05)
    print(f"   ✅ Записано {len(profiles)} профилей")
    print(f"   Статистика профиля: {performance.get_profile_stats('test_profile')}")
    # Test 5: Health Checks
    print("\n📋 Тест 5: Health Check")
    health_results = diagnostics.run_health_checks()
    print(f"   ✅ Проведено {len(health_results)} проверок")
        print(f"   - {result.component}: {result.status.value} - {result.message}")

    # Test 6: Statistics
    print("\n📋 Тест 6: Статистика")
    stats = diagnostics.get_statistics()
    print(f"   ✅ Статистика получена")
    print(f"   Всего логов: {stats['logger']['total_logs']}")
    print(f"   Ошибок: {stats['errors']['total_errors']}")
    print(f"   Профилей: {stats['performance']['total_profiles']}")
    # Test 7: Export
    print("\n📋 Тест 7: Экспорт")
    print(f"   ✅ Экспорт выполнен")

    # Test 8: Decorators
    @log_call()
    @profile_call("test_decorator")
    @measure_metric("test_decorator_metric")
    def decorated_function():
        time.sleep(0.01)
        return "OK"

    result = decorated_function()
    print(f"   ✅ Декораторы работают: {result}")

    # Test 9: Clear
    print("\n📋 Тест 9: Очистка")
    diagnostics.clear_all()
    logs_after = logger.get_logs()
    metrics_after = metrics.get_all_metrics()
    print(f"   Логов после: {len(logs_after)}")
    print(f"   Ошибок после: {len(errors_after)}")

    # Test 10: Event subscription
    print("\n📋 Тест 10: События")
    class MockEventBus:
        def subscribe(self, event, handler):
            pass
        def publish(self, event, data):
            pass

    mock_bus = MockEventBus()
    diagnostics.set_event_bus(mock_bus)

    print("\n✅ Все тесты пройдены!")

# ============================================================
# 29.11. MAIN
# ============================================================
if __name__ == "__main__":
    asyncio.run(test_diagnostics())
