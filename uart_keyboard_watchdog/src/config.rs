use std::time::Duration;

#[derive(Debug, Clone)]
pub(crate) struct Config {
    pub(crate) persist_property: String,
    pub(crate) log_tag: String,
    pub(crate) device_name: String,
    pub(crate) state_poll_interval: Duration,
    pub(crate) node_wait_interval: Duration,
}

impl Config {
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

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::Config;

    #[test]
    fn uses_defaults_when_environment_is_missing() {
        let config = Config::from_lookup(|_| None);

        assert_eq!(config.persist_property, "persist.sys.uart.dock");
        assert_eq!(config.log_tag, "uart_keyboard_watchdog");
        assert_eq!(config.device_name, "mid_input");
        assert_eq!(config.state_poll_interval, Duration::from_millis(250));
        assert_eq!(config.node_wait_interval, Duration::from_secs(1));
    }
}
