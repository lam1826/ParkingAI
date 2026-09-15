// Older responses omit is_active. Keep that compatibility without mutating
// the full catalog used to display history and reactivate disabled types.
export function admissionVehicleTypes(types = []) {
  return types.filter((type) => type.is_active === true || type.is_active === undefined);
}

export function admissionTypeId(types, selectedId) {
  return selectedId && admissionVehicleTypes(types).some((type) => Number(type.id) === Number(selectedId))
    ? selectedId : "";
}
