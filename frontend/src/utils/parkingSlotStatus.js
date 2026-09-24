export function getParkingSlotVisualStatus(slot, zone, vehicleType, availability) {
  if (!slot?.is_active || !zone?.is_active || vehicleType?.is_active === false) return "inactive";
  if (slot.is_occupied || availability?.is_occupied) return "occupied";
  if (availability === null) return "unknown";
  if (availability?.reserved || availability?.available_now === false) return "reserved";
  return "available";
}
