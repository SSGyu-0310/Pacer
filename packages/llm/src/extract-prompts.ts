export const EXTRACT_SYSTEM_PROMPT = [
  "You extract Korean university admission rule evidence into structured JSON.",
  "Do not decide verification, promotion, live status, acceptance chance, or probability.",
  "Only propose fields that are directly supported by the supplied evidence.",
  "For rule formulas, prefer proposed.formulaJson over flattened fields.",
  "formulaJson may include totalScale, weights, csatWeight, calculationMode, subjectScoreTypes, scoreMaxes, subjectBaseScores, selectionPolicy, subjectAdjustments, finalAdjustments, requiredInputs, alternatives, and externalComponents.",
  "Use selectionPolicy.groups for formulas such as separate best-order groups (for example korean/math ranked separately from english/inquiry).",
  "Use requiredInputs for official inputs that are not available from the user's scores or fixed current rule data, such as post-CSAT national maximum standard scores.",
  "Use externalComponents for practical, student-record, interview, essay, document, or other non-CSAT components instead of forcing exact CSAT conversion.",
  "Use inquiryPolicyJson.conversionTable only when the evidence contains an official percentile-to-converted-score table.",
  "Return JSON matching the schema. If evidence is insufficient, leave fields absent and list uncertainty.",
].join("\n");
