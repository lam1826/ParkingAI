import { Grid } from "@mui/material";
import SummaryCard from "./SummaryCard";

const SummarySection = ({ data, loading }) => {
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <SummaryCard
          title="Doanh thu hôm nay"
          value={data?.total_revenue_today?.toLocaleString()}
          unit="VNĐ"
          loading={loading}
        />
      </Grid>

      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <SummaryCard
          title="Lượt xe hôm nay"
          value={data?.total_vehicles_today}
          unit="Xe"
          loading={loading}
        />
      </Grid>

      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <SummaryCard
          title="Xe đang trong bãi"
          value={data?.vehicles_currently_inside}
          unit="Xe"
          loading={loading}
        />
      </Grid>

      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <SummaryCard
          title="Tỷ lệ lấp đầy"
          value={data?.occupancy_rate_percentage}
          unit="%"
          loading={loading}
        />
      </Grid>
    </Grid>
  );
};

export default SummarySection;