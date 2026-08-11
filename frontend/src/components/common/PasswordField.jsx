import { useState } from "react";
import { IconButton, InputAdornment, TextField, Tooltip } from "@mui/material";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";

export default function PasswordField({ label = "Mật khẩu", slotProps, ...props }) {
  const [visible, setVisible] = useState(false);

  return (
    <TextField
      {...props}
      label={label}
      type={visible ? "text" : "password"}
      slotProps={{
        ...slotProps,
        input: {
          ...slotProps?.input,
          endAdornment: (
            <InputAdornment position="end">
              <Tooltip title={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}>
                <IconButton
                  edge="end"
                  onClick={() => setVisible((current) => !current)}
                  onMouseDown={(event) => event.preventDefault()}
                  aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                >
                  {visible ? <VisibilityOffIcon /> : <VisibilityIcon />}
                </IconButton>
              </Tooltip>
            </InputAdornment>
          ),
        },
      }}
    />
  );
}
