import type {
  DeepSeekReport,
  DemoResponse,
  RealResearchReport,
  ResearchDataSource,
  ResearchResult
} from "./types";
import { ui } from "@/i18n";

type ResearchReportFetchers = {
  fetchRealReport: (runId: string) => Promise<RealResearchReport>;
  fetchDemo: () => Promise<DemoResponse>;
  fetchMockReport: (result: ResearchResult) => Promise<DeepSeekReport>;
};

export type ResearchReportLoadResult =
  | {
      dataSource: "real_artifacts";
      report: RealResearchReport;
      demo: null;
    }
  | {
      dataSource: "mock_demo";
      report: DeepSeekReport;
      demo: DemoResponse;
    };

export async function loadResearchReportForSource(
  dataSource: ResearchDataSource,
  selectedRunId: string | null,
  fetchers: ResearchReportFetchers
): Promise<ResearchReportLoadResult> {
  if (dataSource === "real_artifacts") {
    if (!selectedRunId) {
      throw new Error(ui.errors.realRunRequired);
    }
    return {
      dataSource: "real_artifacts",
      report: await fetchers.fetchRealReport(selectedRunId),
      demo: null
    };
  }

  if (dataSource === "mock_demo") {
    const demo = await fetchers.fetchDemo();
    return {
      dataSource: "mock_demo",
      report: await fetchers.fetchMockReport(demo.result),
      demo
    };
  }

  throw new Error(ui.errors.apiUnavailable);
}
