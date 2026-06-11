/// Latest dock state observed from input.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ObservedState {
    /// Dock disconnected.
    Detached,
    /// Dock connected.
    Attached,
}

/// Property transition requested by the controller.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
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
        self.observe_known(state)
    }

    /// Mark a requested transition as applied.
    pub(crate) fn mark_applied(&mut self, transition: Transition) {
        self.applied_state = Some(matches!(transition, Transition::ApplyAttached));
    }

    fn observe_known(&mut self, state: ObservedState) -> Option<Transition> {
        let attached = matches!(state, ObservedState::Attached);
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
