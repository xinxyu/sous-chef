import { Component, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RecipeService, Recipe } from '../recipe.service';
import { User } from '../auth.service';
import { jsPDF } from 'jspdf';

@Component({
  selector: 'app-scrape-tab',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './scrape-tab.component.html',
  styleUrls: ['./scrape-tab.component.scss'],
})
export class ScrapeTabComponent {
  recipe = input<Recipe | null>(null);
  steps = input<string[]>([]);
  currentUser = input<User | null>(null);

  recipeLoaded = output<{ recipe: Recipe; steps: string[] }>();
  recipeSaved = output<Recipe>();
  showLogin = output<void>();

  url = '';
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  constructor(private recipeService: RecipeService) {}

  onScrape(): void {
    this.error.set(null);
    const trimmedUrl = this.url.trim();
    if (!trimmedUrl) {
      this.error.set('Please enter a recipe URL');
      return;
    }

    this.loading.set(true);
    this.recipeService.scrape(trimmedUrl).subscribe({
      next: (data) => {
        const instructions = data.instructions;
        const steps = Array.isArray(instructions)
          ? instructions
          : instructions
            ? [instructions]
            : [];
        this.recipeLoaded.emit({ recipe: data, steps });
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err?.error?.error || 'Failed to scrape recipe');
      },
    });
  }

  onSaveRecipe(): void {
    const r = this.recipe();
    const user = this.currentUser();
    if (!r || !user) return;
    this.saving.set(true);
    this.error.set(null);
    this.recipeService.saveRecipe(r).subscribe({
      next: (savedRecipe) => {
        this.recipeSaved.emit(savedRecipe);
        this.saving.set(false);
      },
      error: (err) => {
        this.saving.set(false);
        this.error.set(err?.error?.error || 'Failed to save recipe');
      },
    });
  }

  exportRecipeToPdf(): void {
    const r = this.recipe();
    if (!r) return;
    const doc = new jsPDF();
    const margin = 20;
    const pageW = doc.internal.pageSize.getWidth();
    let y = 20;
    const lineHeight = 7;
    const maxW = pageW - margin * 2;
    const wrap = (text: string): string[] => doc.splitTextToSize(text, maxW);

    doc.setFontSize(22);
    doc.setFont('helvetica', 'bold');
    const titleLines = wrap(r.title || 'Untitled Recipe');
    doc.text(titleLines, margin, y);
    y += titleLines.length * lineHeight + 8;

    doc.setFontSize(11);
    doc.setFont('helvetica', 'normal');
    const meta: string[] = [];
    if (r.total_time != null) meta.push('Total time: ' + r.total_time);
    if (r.yields) meta.push('Yields: ' + r.yields);
    if (r.host) meta.push('Source: ' + r.host);
    if (meta.length) {
      doc.text(meta.join('  •  '), margin, y);
      y += lineHeight + 10;
    }
    if (r.source_url) {
      doc.setFont('helvetica', 'bold');
      doc.text('Reference URL:', margin, y);
      y += lineHeight;
      doc.setFont('helvetica', 'normal');
      const urlLines = wrap(r.source_url);
      doc.text(urlLines, margin, y);
      y += urlLines.length * lineHeight + 10;
    }

    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text('Ingredients', margin, y);
    y += lineHeight + 4;
    doc.setFontSize(11);
    doc.setFont('helvetica', 'normal');
    for (const ing of r.ingredients || []) {
      const lines = wrap('• ' + ing);
      if (y + lines.length * lineHeight > 270) {
        doc.addPage();
        y = 20;
      }
      doc.text(lines, margin, y);
      y += lines.length * lineHeight + 2;
    }
    y += 6;

    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text('Instructions', margin, y);
    y += lineHeight + 4;
    doc.setFontSize(11);
    doc.setFont('helvetica', 'normal');
    const steps = Array.isArray(r.instructions) ? r.instructions : r.instructions ? [r.instructions] : [];
    for (let i = 0; i < steps.length; i++) {
      const step = String(steps[i]);
      const lines = wrap((i + 1) + '. ' + step);
      if (y + lines.length * lineHeight > 270) {
        doc.addPage();
        y = 20;
      }
      doc.text(lines, margin, y);
      y += lines.length * lineHeight + 4;
    }

    const filename = (r.title || 'recipe').replace(/[^a-z0-9]+/gi, '-').toLowerCase() + '.pdf';
    doc.save(filename);
  }

  requestShowLogin(): void {
    this.showLogin.emit();
  }
}
