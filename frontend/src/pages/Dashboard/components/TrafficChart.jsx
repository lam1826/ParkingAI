import {
    ResponsiveContainer,
    BarChart,
    Bar,
    CartesianGrid,
    Tooltip,
    XAxis,
    YAxis
} from "recharts";

import ChartCard from "./ChartCard";

const TrafficChart = ({ data = [] }) => {

    return (

        <ChartCard title="Lưu lượng xe">

            <ResponsiveContainer
                width="100%"
                height={320}
            >

                <BarChart data={data}>

                    <CartesianGrid strokeDasharray="3 3"/>

                    <XAxis dataKey="hour"/>

                    <YAxis/>

                    <Tooltip/>

                    <Bar
                        dataKey="count"
                        radius={[8,8,0,0]}
                    />

                </BarChart>

            </ResponsiveContainer>

        </ChartCard>

    );

};

export default TrafficChart;