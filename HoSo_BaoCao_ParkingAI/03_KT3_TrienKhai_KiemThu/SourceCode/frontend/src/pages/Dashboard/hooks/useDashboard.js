// File: src/pages/Dashboard/hooks/useDashboard.js
import { useEffect, useRef, useState, useCallback } from "react";
import dashboardService from "../services/dashboardService";
import { createLatestRequestGate } from "../../../utils/latestRequestGate";

const initialError = {
  open: false,
  message: "",
};

const useDashboard = () => {
  const dashboardRequestGate = useRef(null);
  if (dashboardRequestGate.current === null) {
    dashboardRequestGate.current = createLatestRequestGate();
  }

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

  const loadSummary = useCallback(async (requestGate, requestGeneration) => {
    try {
      setLoading(true);
      const response = await dashboardService.getSummary();
      if (!requestGate.isCurrent(requestGeneration)) return;
      setData(response);
    } catch (err) {
      if (!requestGate.isCurrent(requestGeneration)) return;
      setError({
        open: true,
        message: err?.response?.data?.detail || "Không thể tải dữ liệu Dashboard.",
      });
    } finally {
      if (requestGate.isCurrent(requestGeneration)) setLoading(false);
    }
  }, []);

  const loadAIInsight = useCallback(async (requestGate, requestGeneration) => {
    try {
      setAiLoading(true);
      const response = await dashboardService.getAIInsight();
      if (!requestGate.isCurrent(requestGeneration)) return;
      setAiData(response);
    } catch (err) {
      if (!requestGate.isCurrent(requestGeneration)) return;
      console.error("Dashboard operational suggestion error:", err);
      setAiData({ insight: "Không thể tải gợi ý vận hành." });
    } finally {
      if (requestGate.isCurrent(requestGeneration)) setAiLoading(false);
    }
  }, []);

  const loadRecentSessions = useCallback(async (requestGate, requestGeneration) => {
    try {
      setSessionsLoading(true);
      const response = await dashboardService.getRecentSessions();
      if (!requestGate.isCurrent(requestGeneration)) return;
      setRecentSessions(response.data || response);
    } catch (err) {
      if (requestGate.isCurrent(requestGeneration)) {
        console.error("Recent Sessions Error:", err);
      }
    } finally {
      if (requestGate.isCurrent(requestGeneration)) setSessionsLoading(false);
    }
  }, []);

  // THÊM MỚI: Load dữ liệu cho 2 biểu đồ
  const loadChartsData = useCallback(async (requestGate, requestGeneration) => {
    try {
      setChartsLoading(true);
      const [revRes, trafRes] = await Promise.all([
        dashboardService.getRevenueChart(),
        dashboardService.getTrafficChart(),
      ]);
      if (!requestGate.isCurrent(requestGeneration)) return;
      setRevenueData(revRes.data || revRes);
      setTrafficData(trafRes.data || trafRes);
    } catch (err) {
      if (requestGate.isCurrent(requestGeneration)) {
        console.error("Charts Data Error:", err);
      }
    } finally {
      if (requestGate.isCurrent(requestGeneration)) setChartsLoading(false);
    }
  }, []);

  const refreshDashboard = useCallback(async () => {
    const requestGate = dashboardRequestGate.current;
    const requestGeneration = dashboardRequestGate.current.begin();
    await Promise.all([
      loadSummary(requestGate, requestGeneration),
      loadAIInsight(requestGate, requestGeneration),
      loadRecentSessions(requestGate, requestGeneration),
      loadChartsData(requestGate, requestGeneration),
    ]);
  }, [loadSummary, loadAIInsight, loadRecentSessions, loadChartsData]);

  useEffect(() => {
    refreshDashboard();
    return () => dashboardRequestGate.current.invalidate();
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
