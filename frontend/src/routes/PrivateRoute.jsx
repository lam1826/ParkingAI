import { Navigate, useLocation } from "react-router-dom";
import { withNext } from "../utils/safeNext";

// Anonymous visitors land on the public lot page from "/"; any other private
// path goes to login with a same-origin continuation so the chosen flow
// (buy a ticket, reserve) resumes after signing in.
const PrivateRoute = ({ children }) => {
  const token = localStorage.getItem("token");
  const location = useLocation();

  if (!token) {
    if (location.pathname === "/") {
      return <Navigate to="/gioi-thieu" replace />;
    }
    return <Navigate to={withNext("/login", `${location.pathname}${location.search}`)} replace />;
  }

  return children;
};

export default PrivateRoute;
