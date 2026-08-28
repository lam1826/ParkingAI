import { Box, Typography } from "@mui/material";

export default function BrandLogo({
  size = 40,
  inverse = false,
  orientation = "horizontal",
  tagline,
  headingComponent = "div",
}) {
  const vertical = orientation === "vertical";

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: vertical ? "column" : "row",
        alignItems: "center",
        gap: vertical ? 1.5 : 1.25,
        minWidth: 0,
      }}
    >
      <Box
        component="img"
        src="/brand-mark.svg"
        alt=""
        aria-hidden="true"
        sx={{ width: size, height: size, flex: "0 0 auto" }}
      />
      <Box sx={{ minWidth: 0, textAlign: vertical ? "center" : "left" }}>
        <Typography
          component={headingComponent}
          sx={{
            color: inverse ? "common.white" : "text.primary",
            fontSize: vertical ? "1.5rem" : "1.125rem",
            fontWeight: 750,
            letterSpacing: "-0.025em",
            lineHeight: 1.15,
          }}
        >
          ParkingAI
        </Typography>
        {tagline && (
          <Typography
            variant="body2"
            sx={{
              color: inverse ? "rgba(255, 255, 255, 0.82)" : "text.secondary",
              mt: 0.5,
            }}
          >
            {tagline}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
