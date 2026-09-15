import { createElement } from "react";
import { Box } from "@mui/material";
import Markdown from "react-markdown";

const allowedElements = ["p", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em"];
const components = { h1: "h3", h2: "h3", h3: "h3", h4: "h4", h5: "h4", h6: "h4" };

// Analysis text is untrusted. Raw HTML is skipped; links become their text and
// images are omitted. No plugin may turn model output into HTML or network loads.
export default function AIResultContent({ content }) {
  return createElement(Box, { sx: {
    maxWidth: "75ch", mt: 1.5, overflowWrap: "anywhere", lineHeight: 1.75,
    "& p": { my: 1.25 }, "& ul, & ol": { my: 1.25, pl: 3 }, "& li": { mb: 0.5 },
    "& li > p": { my: 0.5 }, "& h3, & h4": { fontSize: "1.05rem", lineHeight: 1.5, mt: 2.5, mb: 1, fontWeight: 700 },
    "& > :first-child": { mt: 0 }, "& > :last-child": { mb: 0 },
  } }, createElement(Markdown, {
    allowedElements, components, skipHtml: true, unwrapDisallowed: true, urlTransform: () => "",
  }, typeof content === "string" ? content : ""));
}
