import { admissionVehicleTypes } from "../../utils/admissionVehicleTypes.js";

export function admissionChoices(types, slots, requestedType = "", requestedSlot = "") {
  const activeTypes = admissionVehicleTypes(types);
  // A removed selection must be chosen again; an untouched form may use the first type.
  const type = requestedType ? activeTypes.find(row => String(row.id) === String(requestedType)) : activeTypes[0];
  const available = (slots || []).filter(row => type && row.available_now === true && Number(row.vehicle_type_id) === Number(type.id));
  const slot = requestedSlot ? available.find(row => String(row.id) === String(requestedSlot)) : available[0];
  return { types: activeTypes, typeId: type?.id ?? "", requiresPlate: type?.requires_plate !== false, slots: available, slotId: slot?.id ?? "" };
}

export function operationLookup(value, kind = "plate") {
  const query = String(value || "").trim();
  if (!query) throw new Error(kind === "ticket" ? "Hãy nhập mã lượt trên vé." : "Hãy nhập biển số xe.");
  return { status: "active", limit: 25, offset: 0, ...(kind === "ticket" ? { session_id: query } : { license_plate: query.toUpperCase() }) };
}

export function operationTypeName(session, types = [], slots = []) {
  if (session?.vehicle_type_name) return session.vehicle_type_name;
  const slot = slots.find(row => String(row.id) === String(session?.parking_slot_id));
  const typeId = session?.vehicle_type_id ?? slot?.vehicle_type_id;
  return types.find(row => String(row.id) === String(typeId))?.name || "—";
}
