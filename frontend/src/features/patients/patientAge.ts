/**
 * Age in whole years from a date of birth, falling back to a year of birth.
 *
 * Shared by the patient list and the register preview so both screens agree
 * on the value. Kept in its own module because the fast-refresh lint rule
 * forbids exporting a plain helper from a file that also exports a
 * component.
 */
export function calculatePatientAge(
  dobString?: string | null,
  yob?: number | null,
): number | null {
  if (dobString) {
    const birth = new Date(dobString);
    const diff = Date.now() - birth.getTime();
    const ageDate = new Date(diff);
    return Math.abs(ageDate.getUTCFullYear() - 1970);
  }
  if (yob) {
    return new Date().getFullYear() - yob;
  }
  return null;
}
