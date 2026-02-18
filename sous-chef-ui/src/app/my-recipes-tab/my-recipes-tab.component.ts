import { Component, input, output } from '@angular/core';
import { Recipe } from '../recipe.service';

@Component({
  selector: 'app-my-recipes-tab',
  standalone: true,
  imports: [],
  templateUrl: './my-recipes-tab.component.html',
  styleUrls: ['./my-recipes-tab.component.scss'],
})
export class MyRecipesTabComponent {
  savedRecipes = input<Recipe[]>([]);
  selectedRecipeIds = input<Set<string>>(new Set());

  loadRecipe = output<string>();
  deleteRecipe = output<string>();
  createMenu = output<void>();
  toggleSelection = output<string>();

  isSelected(recipeId: string): boolean {
    return this.selectedRecipeIds().has(recipeId);
  }

  onLoadRecipe(id: string): void {
    this.loadRecipe.emit(id);
  }

  onDeleteRecipe(id: string, event: Event): void {
    event.stopPropagation();
    this.deleteRecipe.emit(id);
  }

  onToggleSelection(recipeId: string, event?: Event): void {
    event?.stopPropagation();
    this.toggleSelection.emit(recipeId);
  }

  onCreateMenu(): void {
    this.createMenu.emit();
  }
}
