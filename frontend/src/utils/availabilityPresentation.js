// Count only the active inventory returned by the scoped availability endpoint.
// Never infer admission capacity from a physically empty slot alone.
export function availabilityByZone(slots = []) {
  const zones = new Map();
  for (const slot of slots) {
    const key = slot.zone_id ?? slot.zone_name;
    if (!zones.has(key)) zones.set(key, { id: key, name: slot.zone_name || "Chưa xác định khu vực",
      total: 0, occupied: 0, reserved: 0, available: 0 });
    const zone = zones.get(key);
    zone.total += 1;
    if (slot.is_occupied) zone.occupied += 1;
    else if (slot.available_now === true) zone.available += 1;
    else if (slot.reserved === true) zone.reserved += 1;
  }
  return [...zones.values()];
}

export function availabilityLabel(slot) {
  if (slot.is_occupied) return "Đang có xe";
  if (slot.available_now === true) return "Có thể nhận xe";
  if (slot.reserved === true) return "Đã dành chỗ";
  return "Chưa xác nhận khả năng nhận xe";
}
