export type HourCompare = {
  lastHour: number;
  previousHour: number;
  changePct: number | null;
  direction: 'up' | 'down' | 'flat';
};

export function computeHourChange(lastHour: number, previousHour: number): HourCompare {
  if (previousHour === 0 && lastHour === 0) {
    return { lastHour, previousHour, changePct: 0, direction: 'flat' };
  }
  if (previousHour === 0) {
    return { lastHour, previousHour, changePct: null, direction: 'up' };
  }
  const changePct = Math.round(((lastHour - previousHour) / previousHour) * 1000) / 10;
  const direction = changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'flat';
  return { lastHour, previousHour, changePct, direction };
}
