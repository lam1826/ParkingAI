import { Card, CardContent, Typography } from "@mui/material";

const ChartCard = ({ title, children }) => {
    return (
        <Card
            sx={{
                borderRadius: 3,
                boxShadow: 3,
                height: "100%"
            }}
        >
            <CardContent>

                <Typography
                    variant="h6"
                    fontWeight="bold"
                    sx={{ mb: 2 }}
                >
                    {title}
                </Typography>

                {children}

            </CardContent>
        </Card>
    );
};

export default ChartCard;