export function getParkingSlotVisualStatus(slot, zone) {
  if (!slot?.is_active || !zone?.is_active) return "inactive";
  return slot.is_occupied ? "occupied" : "available";
}
