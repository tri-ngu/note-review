export interface CheckpointTotals {
  totalWeight: number;
  totalQuestions: number;
  isBalanced: boolean;
}

const WEIGHT_TOLERANCE = 0.05;

export function computeCheckpointTotals(
  allocations: { weight_percentage: number; question_count: number }[],
): CheckpointTotals {
  const totalWeight = allocations.reduce((sum, a) => sum + a.weight_percentage, 0);
  const totalQuestions = allocations.reduce((sum, a) => sum + a.question_count, 0);
  const isBalanced = Math.abs(totalWeight - 100) <= WEIGHT_TOLERANCE;
  return { totalWeight, totalQuestions, isBalanced };
}
