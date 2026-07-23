use std::time::Duration;

#[derive(Debug)]
/// Runtime configuration for the watchdog service.
pub(crate) struct Config {
    /// Property updated when the dock state changes.
    pub(crate) persist_property: String,
    /// Log tag used for Android logging.
    pub(crate) log_tag: String,
    /// Input device name to watch for the dock switch.
    pub(crate) device_name: String,
    /// Poll interval for dock state checks.
    pub(crate) state_poll_interval: Duration,
    /// Interval between device discovery retries.
    pub(crate) node_wait_interval: Duration,
}

impl Config {
    /// Load configuration from environment variables.
    pub(crate) fn from_env() -> Self {
        Self::from_lookup(|key| std::env::var(key).ok())
    }

    fn from_lookup(lookup: impl Fn(&str) -> Option<String>) -> Self {
        Self {
            persist_property: env_or(&lookup, "PROP", "persist.sys.uart.dock"),
            log_tag: env_or(&lookup, "LOGTAG", "uart_keyboard_watchdog"),
            device_name: env_or(&lookup, "MID_INPUT_NAME", "mid_input"),
            state_poll_interval: Duration::from_millis(env_u64(&lookup, "STATE_POLL_MS", 250)),
            node_wait_interval: Duration::from_secs(env_u64(&lookup, "NODE_WAIT_SECS", 1)),
        }
    }
}

fn env_or(lookup: &impl Fn(&str) -> Option<String>, key: &str, default: &str) -> String {
    lookup(key).unwrap_or_else(|| default.to_owned())
}

fn env_u64(lookup: &impl Fn(&str) -> Option<String>, key: &str, default: u64) -> u64 {
    lookup(key)
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(default)
}

