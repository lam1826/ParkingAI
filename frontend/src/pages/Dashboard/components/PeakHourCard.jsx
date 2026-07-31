import {
  Card,
  CardContent,
  Typography,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
} from "@mui/material";

const PeakHourCard = ({ loading, data = [] }) => {
  return (
    <Card
      sx={{
        height: "100%",
        boxShadow: 3,
        borderRadius: 3,
      }}
    >
      <CardContent>
        <Typography
          variant="h6"
          fontWeight="bold"
          gutterBottom
        >
          Top 5 khung giờ cao điểm
        </Typography>

        {loading ? (
          <Skeleton
            variant="rectangular"
            width="100%"
            height={220}
            sx={{
              mt: 2,
              borderRadius: 2,
            }}
          />
        ) : (
          <TableContainer sx={{ mt: 1 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>
                    <strong>Khung giờ</strong>
                  </TableCell>

                  <TableCell align="right">
                    <strong>Lượt xe</strong>
                  </TableCell>
                </TableRow>
              </TableHead>

              <TableBody>
                {data.length > 0 ? (
                  data.map((row, index) => (
                    <TableRow
                      key={index}
                      hover
                    >
                      <TableCell>
                        {row.hour}
                      </TableCell>

                      <TableCell align="right">
                        <Chip
                          label={row.count}
                          color="primary"
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell
                      colSpan={2}
                      align="center"
                    >
                      Chưa có dữ liệu giao dịch trong ngày
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
};

export default PeakHourCard;