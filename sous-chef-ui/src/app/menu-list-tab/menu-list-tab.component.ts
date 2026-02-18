import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Recipe } from '../recipe.service';

@Component({
  selector: 'app-menu-list-tab',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './menu-list-tab.component.html',
  styleUrls: ['./menu-list-tab.component.scss'],
})
export class MenuListTabComponent implements OnChanges {
  @Input() menuRecipes: Recipe[] = [];

  @Output() changeSelection = new EventEmitter<void>();

  shoppingListView: 'combined' | 'byRecipe' = 'byRecipe';
  combinedIngredients: { name: string; amounts: string[] }[] = [];
  copyFeedback = false;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['menuRecipes'] && this.menuRecipes?.length) {
      this.buildCombinedIngredients();
    }
  }

  private buildCombinedIngredients(): void {
    const allIngredients: string[] = [];
    this.menuRecipes.forEach((r) => {
      (r.ingredients || []).forEach((i) => allIngredients.push(i));
    });
    this.combinedIngredients = this.combineIngredients(allIngredients);
  }

  private getAmountPhrase(ingredient: string): string {
    const trimmed = ingredient.trim();
    const match = trimmed.match(
      /^([\d¼½¾⅓⅔⅛⅜⅝⅞\.\-\/\s]+(?:cup|cups|tbsp|tablespoon|tablespoons|tsp|teaspoon|teaspoons|ounce|ounces|oz|pound|pounds|lb|lbs|clove|cloves|can|cans|package|packages|pinch|dash|slice|slices|piece|pieces)?\s*)/i
    );
    return match ? match[1].trim() : '';
  }

  private normalizeIngredientKey(ingredient: string): string {
    const lower = ingredient.trim().toLowerCase();
    const amount = this.getAmountPhrase(ingredient);
    if (!amount) return lower;
    const rest = lower.slice(amount.length).replace(/\s+/g, ' ').trim();
    return rest || lower;
  }

  private combineIngredients(ingredients: string[]): { name: string; amounts: string[] }[] {
    const map = new Map<string, string[]>();
    for (const ing of ingredients) {
      const trimmed = ing.trim();
      const amount = this.getAmountPhrase(ing);
      const key = this.normalizeIngredientKey(ing);
      const displayAmount = amount || trimmed;
      if (!map.has(key)) map.set(key, []);
      const list = map.get(key)!;
      if (!list.includes(displayAmount)) list.push(displayAmount);
    }
    return Array.from(map.entries())
      .map(([name, amounts]) => ({ name, amounts }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  getShoppingListAsText(): string {
    const lines: string[] = ['Shopping List', ''];
    for (const r of this.menuRecipes) {
      lines.push(r.title || 'Untitled Recipe');
      lines.push('');
      for (const ing of r.ingredients || []) {
        lines.push('• ' + ing);
      }
      lines.push('');
    }
    return lines.join('\n').trim();
  }

  async copyShoppingList(): Promise<void> {
    const text = this.getShoppingListAsText();
    try {
      await navigator.clipboard.writeText(text);
      this.copyFeedback = true;
      setTimeout(() => (this.copyFeedback = false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      this.copyFeedback = true;
      setTimeout(() => (this.copyFeedback = false), 2000);
    }
  }

  onChangeSelection(): void {
    this.changeSelection.emit();
  }
}
