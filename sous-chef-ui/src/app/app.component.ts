import { Component, effect, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RecipeService, Recipe } from './recipe.service';
import { AuthService, User } from './auth.service';
import { ScrapeTabComponent } from './scrape-tab/scrape-tab.component';
import { MyRecipesTabComponent } from './my-recipes-tab/my-recipes-tab.component';
import { MenuListTabComponent } from './menu-list-tab/menu-list-tab.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    FormsModule,
    ScrapeTabComponent,
    MyRecipesTabComponent,
    MenuListTabComponent,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent {
  readonly title = 'Sous Chef';

  readonly recipe = signal<Recipe | null>(null);
  readonly steps = signal<string[]>([]);
  readonly savedRecipes = signal<Recipe[]>([]);
  readonly activeTab = signal<'scrape' | 'saved' | 'menu'>('scrape');
  readonly selectedRecipeIds = signal<Set<string>>(new Set());
  readonly menuRecipes = signal<Recipe[]>([]);

  readonly showLogin = signal(false);
  readonly showRegister = signal(false);
  readonly authError = signal<string | null>(null);
  readonly authLoading = signal(false);

  loginUsername = '';
  loginPassword = '';
  registerUsername = '';
  registerEmail = '';
  registerPassword = '';

  constructor(
    private recipeService: RecipeService,
    public authService: AuthService
  ) {
    effect(() => {
      const user = this.authService.currentUser();
      if (!user) {
        this.savedRecipes.set([]);
        this.activeTab.set('scrape');
      }
    });
    effect(() => {
      const user = this.authService.currentUser();
      const tab = this.activeTab();
      if (user && tab === 'saved') {
        this.loadSavedRecipes();
      }
    });
  }

  setActiveTab(tab: 'scrape' | 'saved' | 'menu'): void {
    this.activeTab.set(tab);
    const user = this.authService.currentUser();
    if (tab === 'saved' && user) {
      this.loadSavedRecipes();
    }
    if (tab === 'menu') {
      this.buildMenuRecipes();
    }
  }

  onRecipeLoaded(event: { recipe: Recipe; steps: string[] }): void {
    this.recipe.set(event.recipe);
    this.steps.set(event.steps);
  }

  onRecipeSaved(savedRecipe: Recipe): void {
    this.recipe.set(savedRecipe);
    this.loadSavedRecipes();
  }

  loadSavedRecipes(): void {
    const user = this.authService.currentUser();
    if (!user) return;
    this.recipeService.getRecipes().subscribe({
      next: (recipes) => this.savedRecipes.set(recipes),
      error: (err) => console.error('Failed to load saved recipes:', err),
    });
  }

  onLoadRecipe(id: string): void {
    this.activeTab.set('scrape');
    this.recipeService.getRecipe(id).subscribe({
      next: (recipe) => {
        this.recipe.set(recipe);
        const instructions = recipe.instructions;
        const steps = Array.isArray(instructions)
          ? instructions
          : instructions
            ? [instructions]
            : [];
        this.steps.set(steps);
        setTimeout(() => {
          document.querySelector('.recipe')?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      },
      error: () => {
        this.recipe.set(null);
        this.steps.set([]);
      },
    });
  }

  toggleRecipeSelection(recipeId: string): void {
    this.selectedRecipeIds.update((ids) => {
      const next = new Set(ids);
      if (next.has(recipeId)) next.delete(recipeId);
      else next.add(recipeId);
      return next;
    });
  }

  createMenu(): void {
    if (this.selectedRecipeIds().size === 0) return;
    this.activeTab.set('menu');
    this.buildMenuRecipes();
  }

  buildMenuRecipes(): void {
    const saved = this.savedRecipes();
    const ids = this.selectedRecipeIds();
    this.menuRecipes.set(saved.filter((r) => r.id != null && ids.has(r.id)));
  }

  onDeleteRecipe(id: string): void {
    if (!confirm('Are you sure you want to delete this recipe?')) return;
    this.recipeService.deleteRecipe(id).subscribe({
      next: () => {
        this.loadSavedRecipes();
        if (this.recipe()?.id === id) {
          this.recipe.set(null);
          this.steps.set([]);
        }
      },
      error: (err) => console.error(err),
    });
  }

  onLogin(): void {
    this.authError.set(null);
    this.authLoading.set(true);
    this.authService.login(this.loginUsername, this.loginPassword).subscribe({
      next: () => {
        this.authLoading.set(false);
        this.showLogin.set(false);
        this.loginUsername = '';
        this.loginPassword = '';
      },
      error: (err) => {
        this.authLoading.set(false);
        this.authError.set(err?.error?.error || 'Login failed');
      },
    });
  }

  onRegister(): void {
    this.authError.set(null);
    this.authLoading.set(true);
    this.authService
      .register(this.registerUsername, this.registerPassword, this.registerEmail || undefined)
      .subscribe({
        next: () => {
          this.authLoading.set(false);
          this.showRegister.set(false);
          this.registerUsername = '';
          this.registerEmail = '';
          this.registerPassword = '';
        },
        error: (err) => {
          this.authLoading.set(false);
          this.authError.set(err?.error?.error || 'Registration failed');
        },
      });
  }

  onLogout(): void {
    this.authService.logout().subscribe({
      next: () => {
        this.recipe.set(null);
        this.savedRecipes.set([]);
        this.steps.set([]);
        this.selectedRecipeIds.set(new Set());
        this.menuRecipes.set([]);
      },
      error: (err) => console.error('Logout error:', err),
    });
  }
}
