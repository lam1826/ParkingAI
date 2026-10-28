import { useContext } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import { postLoginDestination } from "../pages/Login/loginDestination";
import { nextFromSearch } from "../utils/safeNext";

// B-19 (28/10/2026): a signed-in account never sees the login or registration
// form again. It goes where login sends it (round 2, FE-R2-01): the same role rule,
// so whichever navigation commits last, an internal account never lands on a
// customer-only continuation such as /portal or /reservations.
const GuestRoute = ({ children }) => {
  const { user } = useContext(AuthContext);
  const location = useLocation();
  if (user) return <Navigate to={postLoginDestination(nextFromSearch(location.search), user.role)} replace />;
  return children;
};

export default GuestRoute;
