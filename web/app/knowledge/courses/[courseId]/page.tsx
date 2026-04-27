"use client";

import { useParams } from "next/navigation";

import CourseKnowledgePanel from "@/components/knowledge/CourseKnowledgePanel";

export default function CourseDetailPage() {
  const params = useParams<{ courseId: string }>();
  const courseId = Number(params.courseId);

  return (
    <div className="min-h-[calc(100vh-7rem)] overflow-y-auto p-2 md:p-4">
      <CourseKnowledgePanel courseId={Number.isFinite(courseId) ? courseId : undefined} />
    </div>
  );
}
