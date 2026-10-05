import { admissionVehicleTypes } from "../../utils/admissionVehicleTypes.js";

export function admissionChoices(types, slots, requestedType = "", requestedSlot = "") {
  const served = new Set((slots || []).map(row => Number(row.vehicle_type_id)));
  const activeTypes = admissionVehicleTypes(types).filter(row => served.has(Number(row.id)));
  // A removed selection must be chosen again; an untouched form may use the first type.
  const type = requestedType ? activeTypes.find(row => String(row.id) === String(requestedType)) : activeTypes[0];
  const available = (slots || []).filter(row => type && (row.available_now === true || (row.reserved === true && row.is_occupied === false)) && Number(row.vehicle_type_id) === Number(type.id));
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

// #74 (review 05/10/2026): decide what a camera passage result may do to the
// operator's selected stay. Automatic frames only select when nothing is chosen
// or the current choice was itself made by the camera; explicit clicks are manual.
export function passageSelection(result, options = {}, selected = null) {
  const { updateSelection = true, automatic = false, allowSelection = false, explicit = false, cameraId } = options;
  const refresh = ["entered", "exited"].includes(result?.state);
  const canSelect = explicit || (automatic
    ? allowSelection && (!selected || selected.selectionOrigin === "camera")
    : updateSelection);
  if (!canSelect) return { refresh, action: "none" };
  if (result?.state === "exited") return { refresh, action: selected?.id === result.session_id ? "clear" : "none" };
  if (!result?.session_id) return { refresh, action: "none" };
  return { refresh, action: "select", row: { id: result.session_id, license_plate: result.license_plate, status: "active",
    ...(automatic && !explicit ? { selectionOrigin: "camera", selectionCameraId: cameraId } : {}) } };
}
