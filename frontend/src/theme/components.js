export const components = {
  MuiCssBaseline: { styleOverrides: {
    "::selection": { background: "#cce2ff", color: "#122944" },
    "input,textarea": { caretColor: "#1767bd" },
    "a": { textUnderlineOffset: "4px" },
    ":focus-visible": { outline: "3px solid #438adb", outlineOffset: "3px" },
    "*": { scrollbarColor: "#bacbdf #f3f6fa", scrollbarWidth: "thin" },
  } },
  MuiPaper: { styleOverrides: { outlined: { borderRadius: 14 } } },
  MuiTextField: { defaultProps: { slotProps: { inputLabel: { shrink: true } } } },
  MuiInputLabel: { styleOverrides: { outlined: { position: "static", transform: "none", marginBottom: 7, maxWidth: "100%", fontSize: 13, fontWeight: 600, color: "#34465a", lineHeight: "20px", "&.MuiInputLabel-shrink": { transform: "none" } } } },
  MuiOutlinedInput: { styleOverrides: { root: { minHeight: 46, borderRadius: 7, background: "#fff", "& fieldset": { top: 0, borderColor: "#c7d2df" }, "& legend": { display: "none" } }, input: { padding: "10px 12px", fontSize: 15 } } },
  MuiFormHelperText: { styleOverrides: { root: { marginLeft: 0, fontSize: 12 } } },
  MuiChip: { styleOverrides: { root: { borderRadius: 5, fontSize: 12 } } },
  MuiAppBar: { defaultProps: { elevation: 0 } },
  MuiTab: { styleOverrides: { root: { textTransform: "none", fontWeight: 600, minHeight: 44 } } },
  MuiTableCell: { styleOverrides: { head: { background: "#f8fafc", color: "#596879", fontWeight: 600, fontSize: 12, padding: 12 }, body: { fontVariantNumeric: "tabular-nums", fontSize: 13, padding: "15px 12px" } } },
  MuiCard: {
    styleOverrides: {
      root: {
        borderRadius: 12,
      },
    },
  },

  MuiButton: {
    defaultProps: { disableElevation: true },
    styleOverrides: {
      root: {
        borderRadius: 7,
        minHeight: 44,
        padding: "10px 17px",
        fontSize: 14,
        fontWeight: 600,
        textTransform: "none",
      },
      sizeSmall: { minHeight: 34, padding: "6px 10px", fontSize: 13 },
    },
  },
};
