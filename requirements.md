# Weather-Aware Truck Routing - Project Requirements

## 1. Objective

Build a **React + Django** web application that helps truck drivers choose the safest route by considering **weather, load weight, and travel time**.

The application must compare three route options, assess weather conditions at points along each route based on expected arrival times, and recommend a route using the specified risk priorities.

## 2. Required Technology and Integrations

- **Frontend:** React.
- **Backend:** Django.
- **Routing:** Third-party routing API (no custom routing engine required).
- **Geocoding and weather:** Third-party APIs are permitted.
- **Map:** An interactive map capable of displaying routes, checkpoints, risk information, and a weather heatmap.

The assessment does not mandate particular API providers, a database, deployment platform, or UI library.

## 3. User Inputs

The driver must be able to enter:

1. **Origin**.
2. **Destination**.
3. **Departure date and time**.
4. **Load weight** (in pounds for the provided load rules).

## 4. Functional Requirements

### FR-01 - Generate route alternatives
- Use a routing API to request **three route options** between the selected origin and destination.
- Obtain the route geometry and travel-time estimates needed for weather sampling and map display.

### FR-02 - Sample weather along routes
- Support weather checkpoints at **10, 25, or 50 mile intervals** along each route.
- Estimate when the truck will reach each checkpoint based on the departure time and travel progress.
- Retrieve forecast weather for each checkpoint **at its estimated arrival time**, not merely at the departure time.
- Obtain the wind, rain, and snow measurements needed by the risk rules.

### FR-03 - Classify checkpoint weather risk
- Assign a weather risk level to each checkpoint using the thresholds in Section 5.
- Apply the load-dependent wind overrides in Section 6.
- Make checkpoint risk levels available to the route comparison and map.

### FR-04 - Compare and recommend routes
- Derive route-level risk summaries from checkpoint assessments.
- Recommend a route following the **ordered priorities** in Section 7.
- Show the recommended route and the information used to compare it with the alternatives.

### FR-05 - Visualize routes and checkpoints
Display on an interactive map:
- All three routes.
- Weather checkpoints for each route.
- Risk levels and estimated arrival times (ETAs).
- Route summaries.
- A clear indication of the recommended route.

### FR-06 - Weather heatmap
- Show a weather heatmap along the trip corridor.
- Include a forecast time slider covering **0-48 hours**.
- Update the heatmap according to the selected forecast time.

## 5. Weather Risk Thresholds

Classify each measured condition using the PDF's thresholds:

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| **Wind** | <25 mph | 25-34 mph | 35-44 mph | 45-54 mph | >=55 mph |
| **Rain** | <0.10 in/hr | 0.10-0.25 in/hr | 0.25-0.50 in/hr | 0.50-1.00 in/hr | >1.00 in/hr |
| **Snow** | <0.5 in/hr | 0.5-1.0 in/hr | 1.0-2.0 in/hr | 2.0-3.0 in/hr | >3.0 in/hr |

**Implementation note:** The assessment prints some shared boundary values in adjacent ranges (for example, rain at exactly 0.25 in/hr). Choose and document a consistent non-overlapping boundary convention when implementing; the PDF does not specify one.

## 6. Load-Dependent Wind Rules

Apply these rules in addition to the base weather classification:

1. **Wind >=55 mph:** **No Travel**, regardless of load weight.
2. **Wind 45-54 mph and load >30,000 lb:** **No Travel**.
3. **Wind 35-44 mph and load >40,000 lb:** **Severe**.

The threshold is **strictly greater than** 30,000 lb or 40,000 lb where `>` is shown.

## 7. Route Recommendation Priorities

Prefer routes in this order:

1. **Fewest Severe miles**.
2. **Fewest High miles**.
3. **Lowest average risk**.
4. **Shortest travel time**.

These are **ordered priorities**, not a specified weighted formula. Preserve their order rather than assigning arbitrary weights.

## 8. Acceptance Criteria

- A driver can enter origin, destination, departure date/time, and load weight.
- The app retrieves and displays three route alternatives when the routing provider supplies them.
- Every route is assessed using weather checkpoints spaced at a supported 10/25/50-mile interval.
- Forecast lookups use each checkpoint's estimated arrival time.
- Wind, rain, snow, and load-dependent risk rules produce the expected classifications.
- Route summaries support comparison by Severe miles, High miles, average risk, and travel time.
- The route recommendation follows the four stated priorities in order.
- The map displays routes, checkpoints, risk levels, ETAs, summaries, and the recommendation.
- The corridor weather heatmap supports a 0-48 hour forecast slider.
- The application is hosted, its code is in a GitHub repository, and a 5-10 minute Loom walkthrough is provided.

## 9. Deliverables

1. **GitHub repository** with the application source code.
2. **Hosted application** accessible for review.
3. **5-10 minute Loom walkthrough** demonstrating the application.

## 10. Evaluation Criteria

| Area | Weight |
|---|---:|
| Routes, weather, risk, and recommendation logic | **40%** |
| UI, map, and heatmap smoothness/performance | **40%** |
| Code quality | **15%** |
| Documentation and walkthrough | **5%** |

**Priority:** Correctness and clarity over extra features.

## 11. Decisions Not Defined by the Assessment

These details require implementation decisions; they are **not additional requirements from the PDF**:

- Which routing, geocoding, weather, and map providers to use.
- Whether 10/25/50 miles is user-selectable or configuration-driven.
- How to estimate travel progress between route points, including changing speeds or stopping time.
- How to convert checkpoint classifications into *miles* at each risk level.
- How to combine simultaneous wind, rain, and snow risk into one checkpoint risk rating.
- How to score **average risk**, including risk-level numeric values and any weighting.
- How to handle **No Travel** checkpoints in overall route selection (the listed recommendation order does not explicitly address them).
- How to handle missing forecast data, fewer than three provider-supplied routes, or trips extending beyond forecast coverage.
- Weather heatmap variable, interpolation, corridor width, and rendering approach.
- Timezone handling for driver-entered departure time.

Document these choices in the project README and apply them consistently. Do not present a chosen policy as though the assessment specified it.

---

*Source: "Full Stack Developer - Weather-Aware Truck Routing" assessment (2-page PDF).*