// Counter monthly-pass form decisions (review 05/10/2026 #0, #8, #19).
// The server re-checks every rule; these keep the defaults and choices correct.

const addDays = (isoDate, days) => {
  const value = new Date(`${isoDate}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
};

/**
 * Default renewal period: it starts the day after the selected period ends, or
 * today when that day already passed (coverage is fixed at admission, so a
 * past period buys nothing). Default length stays 30 days.
 */
export function renewalDefaults(endDate, today) {
  const next = addDays(endDate, 1);
  const start = next > today ? next : today;
  return { start_date: start, end_date: addDays(start, 29) };
}

/** A renewal must still cover today or later; the server refuses an elapsed period. */
export function renewalEndsBeforeToday(form, today) {
  return Boolean(form?.end_date) && form.end_date < today;
}

const vehicleOf = (vehicles, vehicleId) => (vehicles || []).find((row) => String(row.id) === String(vehicleId));

/** Customers that may hold a pass for the chosen vehicle: its owner, or anyone for a walk-in vehicle. */
export function ownerChoices(vehicles, customers, vehicleId) {
  const vehicle = vehicleOf(vehicles, vehicleId);
  if (vehicle?.customer_id == null) return customers || [];
  return (customers || []).filter((row) => String(row.id) === String(vehicle.customer_id));
}

/** Customer selection after the vehicle changes: the owner, else keep a still-valid choice. */
export function customerForVehicle(vehicles, customers, vehicleId, currentCustomerId) {
  const vehicle = vehicleOf(vehicles, vehicleId);
  if (vehicle?.customer_id != null) return vehicle.customer_id;
  return ownerChoices(vehicles, customers, vehicleId).some((row) => String(row.id) === String(currentCustomerId)) ? currentCustomerId : "";
}

/** Counter sales are recorded at the deployment's lot when the frontend is scoped to one site. */
export function withCounterSite(body, siteId) {
  return siteId == null ? body : { ...body, site_id: siteId };
}
