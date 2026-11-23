import { useTranslation } from 'react-i18next';
import type { AgentChip as Chip } from '../../utils/agentChips';
import type { AgentChipActions } from './useAgentChipActions';

export function AgentChip({ chip, actions }: { chip: Chip; actions: AgentChipActions }) {
  const { t } = useTranslation();
  const section = chip.kind === 'section';
  return <button
    type="button"
    data-testid={section ? 'ai-chat-chip-section' : 'ai-chat-chip-bench'}
    aria-label={section ? t('aiChat.chips.open_section', { name: chip.name }) : t('aiChat.chips.select_bench', { n: chip.designBench, name: chip.sectionName })}
    onClick={() => section ? actions.openSection({ id: chip.sectionId, name: chip.name }) : actions.selectBench(chip.sectionId, chip.designBench)}
    className="inline rounded-sm border border-border px-1 font-mono text-text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
  >{section ? chip.name : chip.label}</button>;
}
