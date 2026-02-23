import { Component, input, output, signal, computed } from '@angular/core';
import { Recipe } from '../recipe.service';

@Component({
  selector: 'app-menu-list-tab',
  standalone: true,
  imports: [],
  templateUrl: './menu-list-tab.component.html',
  styleUrls: ['./menu-list-tab.component.scss'],
})
export class MenuListTabComponent {
  menuRecipes = input<Recipe[]>([]);

  changeSelection = output<void>();

  readonly shoppingListView = signal<'combined' | 'byRecipe'>('byRecipe');
  readonly copyFeedback = signal(false);

  readonly combinedIngredients = computed(() =>
    this.buildCombinedIngredientsFromRecipes(this.menuRecipes())
  );

  private getAmountPhrase(ingredient: string): string {
    const trimmed = ingredient.trim();
    const match = trimmed.match(
      /^([\d¼½¾⅓⅔⅛⅜⅝⅞\.\-\/\s]+(?:cups|cup|tablespoons|tablespoon|tbsp|teaspoons|teaspoon|tsp|ounces|ounce|oz|pounds|pound|lbs|lb|cloves|clove|cans|can|packages|package|pinch|dash|slices|slice|pieces|piece)?\s*)/i
    );
    if (!match) return '';
    const amount = match[1].trim();
    // Only treat as amount if it contains a number/fraction (avoids ". " or " " as amount)
    const hasNumber = /[\d¼½¾⅓⅔⅛⅜⅝⅞]/.test(amount);
    return hasNumber ? amount : '';
  }

  private normalizeIngredientKey(ingredient: string): string {
    const lower = ingredient.trim().toLowerCase();
    const amount = this.getAmountPhrase(ingredient);
    if (!amount) return lower;
    const rest = lower.slice(amount.length).replace(/\s+/g, ' ').trim();
    // If remainder is empty or a single character (e.g. "2 s" -> "s"), use full string as name
    if (!rest || rest.length <= 1) return lower;
    return rest;
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

  private buildCombinedIngredientsFromRecipes(
    recipes: Recipe[]
  ): { name: string; amounts: string[] }[] {
    const allIngredients: string[] = [];
    for (const r of recipes) {
      for (const i of r.ingredients || []) {
        allIngredients.push(i);
      }
    }
    return this.combineIngredients(allIngredients);
  }

  getShoppingListAsText(): string {
    const lines: string[] = ['Shopping List', ''];
    for (const r of this.menuRecipes()) {
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
      this.copyFeedback.set(true);
      setTimeout(() => this.copyFeedback.set(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      this.copyFeedback.set(true);
      setTimeout(() => this.copyFeedback.set(false), 2000);
    }
  }

  onChangeSelection(): void {
    this.changeSelection.emit();
  }
}
