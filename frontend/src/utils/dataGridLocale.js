import { viVN } from "@mui/x-data-grid/locales";

// B-12 (28/10/2026): DataGrid texts in Vietnamese, including the footer and the
// column-menu labels the bundled viVN locale leaves in English ("1–9 of 9",
// "Biển số column menu").
export const VI_DATA_GRID_TEXT = {
  ...viVN.components.MuiDataGrid.defaultProps.localeText,
  columnMenuAriaLabel: (columnName) => `Menu cột ${columnName}`,
  noColumnsOverlayLabel: "Không có cột",
  noColumnsOverlayManageColumns: "Quản lý cột",
  columnsManagementDeleteIconLabel: "Xóa",
  paginationDisplayedRows: ({ from, to, count, estimated }) =>
    `${from}–${to} trên ${count === -1 ? `hơn ${estimated ?? to}` : count}`,
};
