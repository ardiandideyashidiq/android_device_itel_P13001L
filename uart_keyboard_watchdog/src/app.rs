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

    if let Ok(state) = monitor.current_switch_state() {
        handle_state(config, logger, &mut controller, state);
    }

    loop {
        if !monitor.is_still_present() {
            logger.warn("mid_input device disappeared; rediscovering");
            monitor = wait_for_input_monitor(config, logger);
            if let Ok(state) = monitor.current_switch_state() {
                handle_state(config, logger, &mut controller, state);
            }
            continue;
        }

        let attached = match monitor.wait_for_switch_event() {
            Ok(state) => state,
            Err(error) => {
                logger.warn(format_args!("input event read failed: {error}; rediscovering"));
                monitor = wait_for_input_monitor(config, logger);
                continue;
            }
        };

        handle_state(config, logger, &mut controller, attached);
    }
}

fn handle_state(config: &Config, logger: &Logger, controller: &mut DockController, attached: bool) {
    let observed = if attached {
        ObservedState::Attached
    } else {
        ObservedState::Detached
    };

    if let Some(transition) = controller.observe(observed) {
        let apply = matches!(transition, Transition::ApplyAttached);
        let message = if apply {
            "dock attached; setting dock property"
        } else {
            "dock detached; clearing dock property"
        };
        logger.info(message);

        match android::apply_dock_state(config, apply) {
            Ok(()) => controller.mark_applied(transition),
            Err(error) => logger.warn(format_args!(
                "failed to apply dock {} transition: {error}",
                if apply { "attach" } else { "detach" }
            )),
        }
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
