export function isQuestionCorrect(selected: number[], correctAnswers: number[]): boolean {
  if (selected.length !== correctAnswers.length) return false;
  const sortedSelected = [...selected].sort();
  const sortedCorrect = [...correctAnswers].sort();
  return sortedSelected.every((value, i) => value === sortedCorrect[i]);
}
