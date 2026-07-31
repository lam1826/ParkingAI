// File: src/pages/Dashboard/hooks/useDashboard.js
import { useEffect, useState, useCallback } from "react";
import dashboardService from "../services/dashboardService";

const initialError = {
  open: false,
  message: "",
};

const useDashboard = () => {
  const [data, setData] = useState(null);
  const [aiData, setAiData] = useState(null);
  const [recentSessions, setRecentSessions] = useState([]);
  
  // THÊM MỚI: State cho 2 biểu đồ
  const [revenueData, setRevenueData] = useState([]);
  const [trafficData, setTrafficData] = useState([]);

  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(true);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [chartsLoading, setChartsLoading] = useState(true); // Loading biểu đồ

  const [error, setError] = useState(initialError);

  const loadSummary = useCallback(async () => {
    try {
      setLoading(true);
      const response = await dashboardService.getSummary();
      setData(response);
    } catch (err) {
      setError({
        open: true,
        message: err?.response?.data?.detail || "Không thể tải dữ liệu Dashboard.",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAIInsight = useCallback(async () => {
    try {
      setAiLoading(true);
      const response = await dashboardService.getAIInsight();
      setAiData(response);
    } catch (err) {
      console.error("AI Insight Error:", err);
      setAiData({ insight: "Không thể kết nối AI Service." });
    } finally {
      setAiLoading(false);
    }
  }, []);

  const loadRecentSessions = useCallback(async () => {
    try {
      setSessionsLoading(true);
      const response = await dashboardService.getRecentSessions();
      setRecentSessions(response.data || response);
    } catch (err) {
      console.error("Recent Sessions Error:", err);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  // THÊM MỚI: Load dữ liệu cho 2 biểu đồ
  const loadChartsData = useCallback(async () => {
    try {
      setChartsLoading(true);
      const [revRes, trafRes] = await Promise.all([
        dashboardService.getRevenueChart(),
        dashboardService.getTrafficChart(),
      ]);
      setRevenueData(revRes.data || revRes);
      setTrafficData(trafRes.data || trafRes);
    } catch (err) {
      console.error("Charts Data Error:", err);
    } finally {
      setChartsLoading(false);
    }
  }, []);

  const refreshDashboard = useCallback(async () => {
    await Promise.all([
      loadSummary(),
      loadAIInsight(),
      loadRecentSessions(),
      loadChartsData(),
    ]);
  }, [loadSummary, loadAIInsight, loadRecentSessions, loadChartsData]);

  useEffect(() => {
    refreshDashboard();
  }, [refreshDashboard]);

  const closeError = () => setError(initialError);

  return {
    data,
    aiData,
    recentSessions,
    revenueData,    // Trả về cho Dashboard
    trafficData,    // Trả về cho Dashboard
    loading,
    aiLoading,
    sessionsLoading,
    chartsLoading,  // Trả về trạng thái loading của biểu đồ
    error,
    refreshDashboard,
    closeError,
  };
};

export default useDashboard;