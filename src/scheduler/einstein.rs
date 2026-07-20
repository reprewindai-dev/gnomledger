// src/scheduler/einstein.rs
// Einstein-Markov Dynamic Task Prioritization Engine for Gnomledger
// Governed by the Veklom Runtime Authority

use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PrioritizationFactors {
    pub capability_drift_frequency: f64, // Must be < 0.05%
    pub policy_compliance_probability: f64, // Must be 1.0 (deterministic)
    pub x402_collateralization_ratio: f64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TaskContext {
    pub task_id: String,
    pub factors: PrioritizationFactors,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SchedulerDecision {
    pub task_id: String,
    pub priority_score: f64,
    pub is_executable: bool,
}

pub struct EinsteinScheduler;

impl EinsteinScheduler {
    pub fn new() -> Self {
        Self {}
    }

    /// Evaluates a task and produces a scheduling decision based on the Markov models.
    pub fn evaluate_task(&self, context: &TaskContext) -> SchedulerDecision {
        // Enforce strict deterministic compliance
        if context.factors.policy_compliance_probability < 1.0 {
            return SchedulerDecision {
                task_id: context.task_id.clone(),
                priority_score: 0.0,
                is_executable: false,
            };
        }

        // Halt on drift
        if context.factors.capability_drift_frequency > 0.0005 {
            return SchedulerDecision {
                task_id: context.task_id.clone(),
                priority_score: 0.0,
                is_executable: false,
            };
        }

        // Base priority formula combining Markov estimation with collateral
        let priority_score = (context.factors.x402_collateralization_ratio * 100.0) 
            - (context.factors.capability_drift_frequency * 1000.0);

        SchedulerDecision {
            task_id: context.task_id.clone(),
            priority_score,
            is_executable: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_einstein_scheduler_blocks_non_compliant_tasks() {
        let scheduler = EinsteinScheduler::new();
        let context = TaskContext {
            task_id: "task-001".to_string(),
            factors: PrioritizationFactors {
                capability_drift_frequency: 0.0,
                policy_compliance_probability: 0.99, // Fails deterministic check
                x402_collateralization_ratio: 1.5,
            }
        };

        let decision = scheduler.evaluate_task(&context);
        assert_eq!(decision.is_executable, false);
    }
}
