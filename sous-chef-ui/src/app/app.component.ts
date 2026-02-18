import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RecipeService, Recipe } from './recipe.service';
import { AuthService, User } from './auth.service';
import { Subscription } from 'rxjs';
import { jsPDF } from 'jspdf';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Sous Chef';
  url = '';
  loading = false;
  saving = false;
  error: string | null = null;
  recipe: Recipe | null = null;
  savedRecipes: Recipe[] = [];
  steps: string[] = [];
  activeTab: 'scrape' | 'saved' | 'menu' = 'scrape';
  selectedRecipeIds = new Set<string>();
  menuRecipes: Recipe[] = [];
  combinedIngredients: { name: string; amounts: string[] }[] = [];
  shoppingListView: 'combined' | 'byRecipe' = 'byRecipe';
  copyFeedback = false;
  
  // Auth
  currentUser: User | null = null;
  showLogin = false;
  showRegister = false;
  loginUsername = '';
  loginPassword = '';
  registerUsername = '';
  registerEmail = '';
  registerPassword = '';
  authError: string | null = null;
  authLoading = false;
  
  private subscriptions = new Subscription();

  constructor(
    private recipeService: RecipeService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    const userSub = this.authService.currentUser$.subscribe(user => {
      this.currentUser = user;
      if (user) {
        // Load saved recipes if on saved tab
        if (this.activeTab === 'saved') {
          this.loadSavedRecipes();
        }
      } else {
        this.savedRecipes = [];
        this.activeTab = 'scrape'; // Reset to scrape tab when logged out
      }
    });
    this.subscriptions.add(userSub);
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  onScrape(): void {
    this.error = null;
    this.recipe = null;
    this.steps = [];

    const trimmedUrl = this.url.trim();
    if (!trimmedUrl) {
      this.error = 'Please enter a recipe URL';
      return;
    }

    this.loading = true;
    this.recipeService.scrape(trimmedUrl).subscribe({
      next: (data) => {
        this.recipe = data;
        const instructions = data.instructions;
        this.steps = Array.isArray(instructions)
          ? instructions
          : instructions
          ? [instructions]
          : [];
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.error || 'Failed to scrape recipe';
      },
    });
  }

  exportRecipeToPdf(): void {
    if (!this.recipe) {
      return;
    }
    const r = this.recipe;
    const doc = new jsPDF();
    const margin = 20;
    const pageW = doc.internal.pageSize.getWidth();
    let y = 20;
    const lineHeight = 7;
    const maxW = pageW - margin * 2;

    const wrap = (text: string): string[] => {
      return doc.splitTextToSize(text, maxW);
    };

    doc.setFontSize(22);
    doc.setFont('helvetica', 'bold');
    const titleLines = wrap(r.title || 'Untitled Recipe');
    doc.text(titleLines, margin, y);
    y += titleLines.length * lineHeight + 8;

    doc.setFontSize(11);
    doc.setFont('helvetica', 'normal');
    const meta: string[] = [];
    if (r.total_time != null) {
      meta.push('Total time: ' + r.total_time);
    }
    if (r.yields) {
      meta.push('Yields: ' + r.yields);
    }
    if (r.host) {
      meta.push('Source: ' + r.host);
    }
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
    const ingredients = r.ingredients || [];
    for (const ing of ingredients) {
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

  onSaveRecipe(): void {
    if (!this.recipe || !this.currentUser) {
      return;
    }

    this.saving = true;
    this.error = null;

    this.recipeService.saveRecipe(this.recipe).subscribe({
      next: (savedRecipe) => {
        this.recipe = savedRecipe;
        this.saving = false;
        this.loadSavedRecipes();
      },
      error: (err) => {
        this.saving = false;
        this.error = err?.error?.error || 'Failed to save recipe';
      },
    });
  }

  loadSavedRecipes(): void {
    if (!this.currentUser) {
      return;
    }

    this.recipeService.getRecipes().subscribe({
      next: (recipes) => {
        this.savedRecipes = recipes;
      },
      error: (err) => {
        console.error('Failed to load saved recipes:', err);
      },
    });
  }

  onLoadRecipe(id: string): void {
    this.loading = true;
    this.error = null;
    this.activeTab = 'scrape'; // Switch to scrape tab to show recipe

    this.recipeService.getRecipe(id).subscribe({
      next: (recipe) => {
        this.recipe = recipe;
        const instructions = recipe.instructions;
        this.steps = Array.isArray(instructions)
          ? instructions
          : instructions
          ? [instructions]
          : [];
        this.loading = false;
        // Scroll to recipe after a brief delay to ensure tab switch completes
        setTimeout(() => {
          document.querySelector('.recipe')?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.error || 'Failed to load recipe';
      },
    });
  }

  setActiveTab(tab: 'scrape' | 'saved' | 'menu'): void {
    this.activeTab = tab;
    if (tab === 'saved' && this.currentUser) {
      this.loadSavedRecipes();
    }
    if (tab === 'menu') {
      this.buildMenuAndShoppingList();
    }
  }

  toggleRecipeSelection(recipeId: string, event?: Event): void {
    if (event) {
      event.stopPropagation();
    }
    if (this.selectedRecipeIds.has(recipeId)) {
      this.selectedRecipeIds.delete(recipeId);
    } else {
      this.selectedRecipeIds.add(recipeId);
    }
    this.selectedRecipeIds = new Set(this.selectedRecipeIds);
  }

  isRecipeSelected(recipeId: string): boolean {
    return this.selectedRecipeIds.has(recipeId);
  }

  createMenu(): void {
    if (this.selectedRecipeIds.size === 0) {
      return;
    }
    this.activeTab = 'menu';
    this.buildMenuAndShoppingList();
  }

  buildMenuAndShoppingList(): void {
    this.menuRecipes = this.savedRecipes.filter((r) => r.id && this.selectedRecipeIds.has(r.id));
    const allIngredients: string[] = [];
    this.menuRecipes.forEach((r) => {
      (r.ingredients || []).forEach((i) => allIngredients.push(i));
    });
    this.combinedIngredients = this.combineIngredients(allIngredients);
  }

  /** Normalize ingredient for grouping: lowercase, strip leading amount/unit to get the "ingredient name" part. */
  private normalizeIngredientKey(ingredient: string): string {
    const lower = ingredient.trim().toLowerCase();
    const amount = this.getAmountPhrase(ingredient);
    if (!amount) {
      return lower;
    }
    let rest = lower.slice(amount.length).replace(/\s+/g, ' ').trim();
    return rest || lower;
  }

  /** Extract leading amount phrase (e.g. "1 cup", "2 tbsp") for display. */
  private getAmountPhrase(ingredient: string): string {
    const trimmed = ingredient.trim();
    const match = trimmed.match(/^([\d¼½¾⅓⅔⅛⅜⅝⅞\.\-\/\s]+(?:cup|cups|tbsp|tablespoon|tablespoons|tsp|teaspoon|teaspoons|ounce|ounces|oz|pound|pounds|lb|lbs|clove|cloves|can|cans|package|packages|pinch|dash|slice|slices|piece|pieces)?\s*)/i);
    if (match) {
      return match[1].trim();
    }
    return '';
  }

  private combineIngredients(ingredients: string[]): { name: string; amounts: string[] }[] {
    const map = new Map<string, string[]>();
    for (const ing of ingredients) {
      const trimmed = ing.trim();
      const amount = this.getAmountPhrase(ing);
      const key = this.normalizeIngredientKey(ing);
      const displayAmount = amount || trimmed;
      if (!map.has(key)) {
        map.set(key, []);
      }
      const list = map.get(key)!;
      if (!list.includes(displayAmount)) {
        list.push(displayAmount);
      }
    }
    return Array.from(map.entries())
      .map(([name, amounts]) => ({ name, amounts }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  clearMenuSelection(): void {
    this.selectedRecipeIds.clear();
    this.selectedRecipeIds = new Set();
    this.menuRecipes = [];
    this.combinedIngredients = [];
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
      // Fallback for older browsers: select a hidden textarea
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

  onDeleteRecipe(id: string): void {
    if (!confirm('Are you sure you want to delete this recipe?')) {
      return;
    }

    this.recipeService.deleteRecipe(id).subscribe({
      next: () => {
        this.loadSavedRecipes();
        if (this.recipe?.id === id) {
          this.recipe = null;
          this.steps = [];
        }
      },
      error: (err) => {
        this.error = err?.error?.error || 'Failed to delete recipe';
      },
    });
  }

  onLogin(): void {
    this.authError = null;
    this.authLoading = true;

    this.authService.login(this.loginUsername, this.loginPassword).subscribe({
      next: () => {
        this.authLoading = false;
        this.showLogin = false;
        this.loginUsername = '';
        this.loginPassword = '';
      },
      error: (err) => {
        this.authLoading = false;
        this.authError = err?.error?.error || 'Login failed';
      },
    });
  }

  onRegister(): void {
    this.authError = null;
    this.authLoading = true;

    this.authService.register(
      this.registerUsername,
      this.registerPassword,
      this.registerEmail || undefined
    ).subscribe({
      next: () => {
        this.authLoading = false;
        this.showRegister = false;
        this.registerUsername = '';
        this.registerEmail = '';
        this.registerPassword = '';
      },
      error: (err) => {
        this.authLoading = false;
        this.authError = err?.error?.error || 'Registration failed';
      },
    });
  }

  onLogout(): void {
    this.authService.logout().subscribe({
      next: () => {
        this.recipe = null;
        this.savedRecipes = [];
        this.steps = [];
      },
      error: (err) => {
        console.error('Logout error:', err);
      },
    });
  }
}