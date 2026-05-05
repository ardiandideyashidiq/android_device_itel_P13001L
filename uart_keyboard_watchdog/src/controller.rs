#[derive(Clone, Copy, Debug, Eq, PartialEq)]
/// Latest dock state observed from input.
pub(crate) enum ObservedState {
    /// Dock disconnected.
    Detached,
    /// Dock connected.
    Attached,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
/// Property transition requested by the controller.
pub(crate) enum Transition {
    /// Apply attached state.
    ApplyAttached,
    /// Apply detached state.
    ApplyDetached,
}

/// Tracks desired and applied dock state.
pub(crate) struct DockController {
    desired_state: Option<bool>,
    applied_state: Option<bool>,
}

impl DockController {
    /// Create a fresh controller.
    pub(crate) fn new() -> Self {
        Self {
            desired_state: None,
            applied_state: None,
        }
    }

    /// Record the latest observed state and request a transition when needed.
    pub(crate) fn observe(&mut self, state: ObservedState) -> Option<Transition> {
        match state {
            ObservedState::Detached => self.observe_known(false),
            ObservedState::Attached => self.observe_known(true),
        }
    }

    /// Mark a requested transition as applied.
    pub(crate) fn mark_applied(&mut self, transition: Transition) {
        self.applied_state = Some(matches!(transition, Transition::ApplyAttached));
    }

    fn observe_known(&mut self, attached: bool) -> Option<Transition> {
        self.desired_state = Some(attached);

        if self.applied_state == self.desired_state {
            return None;
        }

        Some(if attached {
            Transition::ApplyAttached
        } else {
            Transition::ApplyDetached
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{DockController, ObservedState, Transition};

    #[test]
    fn requests_attach_when_attached_is_first_seen() {
        let mut controller = DockController::new();

        assert_eq!(
            controller.observe(ObservedState::Attached),
            Some(Transition::ApplyAttached)
        );
    }

    #[test]
    fn retries_attach_until_apply_succeeds() {
        let mut controller = DockController::new();

        assert_eq!(
            controller.observe(ObservedState::Attached),
            Some(Transition::ApplyAttached)
        );
        assert_eq!(
            controller.observe(ObservedState::Attached),
            Some(Transition::ApplyAttached)
        );

        controller.mark_applied(Transition::ApplyAttached);

        assert_eq!(controller.observe(ObservedState::Attached), None);
    }

    #[test]
    fn requests_detach_after_attached_state_was_applied() {
        let mut controller = DockController::new();

        assert_eq!(
            controller.observe(ObservedState::Attached),
            Some(Transition::ApplyAttached)
        );
        controller.mark_applied(Transition::ApplyAttached);

        assert_eq!(
            controller.observe(ObservedState::Detached),
            Some(Transition::ApplyDetached)
        );
    }
}
