use std::io;
use std::thread;

use crate::android;
use crate::config::Config;
use crate::controller::{DockController, ObservedState, Transition};
use crate::input::InputMonitor;
use crate::logging::Logger;

/// Run the watchdog loop.
pub(crate) fn run(config: &Config, logger: &Logger) -> io::Result<()> {
    logger.info("starting uart-keyboard-watchdog");

    let mut monitor = wait_for_input_monitor(config, logger);
    let mut controller = DockController::new();

    loop {
        if !monitor.is_still_present() {
            logger.warn("mid_input device disappeared; rediscovering");
            monitor = wait_for_input_monitor(config, logger);
        }

        let observed = match monitor.current_switch_state() {
            Ok(true) => ObservedState::Attached,
            Ok(false) => ObservedState::Detached,
            Err(error) => {
                logger.warn(format_args!("failed to read dock switch state: {error}"));
                monitor = wait_for_input_monitor(config, logger);
                thread::sleep(config.state_poll_interval);
                continue;
            }
        };

        if let Some(transition) = controller.observe(observed) {
            let attached = matches!(transition, Transition::ApplyAttached);
            let message = if attached {
                "dock attached; setting dock property"
            } else {
                "dock detached; clearing dock property"
            };
            logger.info(message);

            match android::apply_dock_state(config, attached) {
                Ok(()) => controller.mark_applied(transition),
                Err(error) => logger.warn(format_args!(
                    "failed to apply dock {} transition: {error}",
                    if attached { "attach" } else { "detach" }
                )),
            }
        }

        thread::sleep(config.state_poll_interval);
    }
}

fn wait_for_input_monitor(config: &Config, logger: &Logger) -> InputMonitor {
    logger.info("waiting for mid_input");
    loop {
        match InputMonitor::discover(&config.device_name) {
            Ok(Some(monitor)) => {
                logger.info("required dock input is present");
                return monitor;
            }
            Ok(None) => thread::sleep(config.node_wait_interval),
            Err(error) => {
                logger.warn(format_args!("failed to scan input devices: {error}"));
                thread::sleep(config.node_wait_interval);
            }
        }
    }
}
