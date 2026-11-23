import { useTranslation } from 'react-i18next';
import { useSections } from '../../api/hooks';
import { useWorkflowStatus } from '../../hooks/useWorkflowStatus';
import { useSession } from '../../stores/session';

export function EmbeddedWorkflowGuide({ fillDraft, canDraft, suggestionsOnly = false }: { fillDraft: (text: string) => void; canDraft: boolean; suggestionsOnly?: boolean }) {
  const { t } = useTranslation();
  const workflow = useWorkflowStatus();
  const { data: sections = [] } = useSections();
  const selectedByUser = useSession((state) => state.selectedByUser);
  const selectedSection = useSession((state) => state.selectedSection);
  const sectionIsCurrent = selectedByUser && selectedSection !== null && /^[0-9]{1,5}$/.test(selectedSection) && sections.some((section) => String(section.id) === selectedSection);

  if (suggestionsOnly) {
    if (!canDraft || workflow.isProcessing) return null;
    const complete = workflow.hasDesign && workflow.hasTopo && workflow.isComplete;
    const prompt = complete ? (sectionIsCurrent ? 'aiChat.guidance.profile_prompt' : 'aiChat.guidance.review_prompt') : 'aiChat.activity.draft';
    const label = complete ? (sectionIsCurrent ? 'aiChat.guidance.profile_cta' : 'aiChat.guidance.review_cta') : 'aiChat.activity.starter';
    return <div className="mx-auto w-full max-w-3xl px-3 pb-3"><button type="button" onClick={() => fillDraft(t(prompt))} className="rounded border border-border px-2 py-1 text-xs text-text-primary">{t(label)}</button></div>;
  }

  if (workflow.isProcessing) return <div data-testid="ai-chat-guidance" role="status" className="border-b border-border py-3 text-xs text-text-secondary">{t('aiChat.guidance.processing')}</div>;

  if (!workflow.hasDesign || !workflow.hasTopo) {
    const key = workflow.hasDesign ? 'aiChat.guidance.load_topo' : 'aiChat.guidance.load_design';
    return <div data-testid="ai-chat-guidance" className="border-b border-border py-3 text-xs text-text-secondary">
      <p>{t(key)}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {canDraft && <button type="button" onClick={() => fillDraft(t('aiChat.activity.draft'))} className="rounded border border-border px-2 py-1 text-text-primary">{t('aiChat.activity.starter')}</button>}
      </div>
    </div>;
  }

  if (workflow.isComplete) {
    const key = sectionIsCurrent ? 'aiChat.guidance.profile' : 'aiChat.guidance.review';
    const prompt = sectionIsCurrent ? 'aiChat.guidance.profile_prompt' : 'aiChat.guidance.review_prompt';
    return <div data-testid="ai-chat-guidance" className="border-b border-border py-3 text-xs text-text-secondary">
      <p>{t(key)}</p>
      {canDraft && <button type="button" onClick={() => fillDraft(t(prompt))} className="mt-2 rounded border border-border px-2 py-1 text-text-primary">{t(sectionIsCurrent ? 'aiChat.guidance.profile_cta' : 'aiChat.guidance.review_cta')}</button>}
    </div>;
  }

  const stepKey = workflow.nextStep === 'parameters' ? 'parameters' : workflow.nextStep === 'process' ? 'ready' : 'sections';
  return <div data-testid="ai-chat-guidance" className="border-b border-border py-3 text-xs text-text-secondary">
    <p>{t(`aiChat.guidance.${stepKey}`)}</p>
    {canDraft && <button type="button" onClick={() => fillDraft(t('aiChat.activity.draft'))} className="mt-2 rounded border border-border px-2 py-1 text-text-primary">{t('aiChat.activity.starter')}</button>}
  </div>;
}
