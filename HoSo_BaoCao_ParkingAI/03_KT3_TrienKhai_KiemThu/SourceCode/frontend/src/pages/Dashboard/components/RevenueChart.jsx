import {
    ResponsiveContainer,
    AreaChart,
    Area,
    CartesianGrid,
    Tooltip,
    XAxis,
    YAxis
} from "recharts";

import ChartCard from "./ChartCard";

const RevenueChart = ({ data = [] }) => {

    return (

        <ChartCard title="Doanh thu 7 ngày">

            <ResponsiveContainer
                width="100%"
                height={320}
            >

                <AreaChart data={data}>

                    <defs>

                        <linearGradient
                            id="revenue"
                            x1="0"
                            y1="0"
                            x2="0"
                            y2="1"
                        >

                            <stop
                                offset="5%"
                                stopColor="#1976d2"
                                stopOpacity={0.8}
                            />

                            <stop
                                offset="95%"
                                stopColor="#1976d2"
                                stopOpacity={0}
                            />

                        </linearGradient>

                    </defs>

                    <CartesianGrid strokeDasharray="3 3" />

                    <XAxis dataKey="day" />

                    <YAxis />

                    <Tooltip />

                    <Area
                        dataKey="revenue"
                        stroke="#1976d2"
                        fill="url(#revenue)"
                    />

                </AreaChart>

            </ResponsiveContainer>

        </ChartCard>

    );

};

export default RevenueChart;